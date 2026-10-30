import asyncio
import json
import time
from urllib.parse import urlsplit
from pydantic_core import from_json
from sqlalchemy import select
from .agents import Result, PROMPTS
from . import models as m
from .schemas import CodexResearchResult
from .codex_runtime import CodexError


class CodexProvider:
    kind = "codex"

    def __init__(self, config, runtime, sessions):
        self.config = config
        self.runtime = runtime
        self.sessions = sessions
        self.loaded = {}

    def model(self, agent):
        return (
            getattr(self.config, f"codex_{agent}_model")
            or self.config.codex_model
            or "codex-default"
        )

    async def thread(self, scope, agent, channel):
        if not scope:
            raise CodexError("An iteration scope is required")
        key = (scope, agent, channel)
        if self.loaded.get(key, ())[0:1] == (self.runtime.generation,):
            return self.loaded[key][1]
        options = {
            "model": None
            if self.model(agent) == "codex-default"
            else self.model(agent),
            "cwd": self.runtime.workspace,
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "developerInstructions": PROMPTS[agent],
            "config": {"web_search": "live" if channel == "research" else "disabled"},
        }
        async with self.sessions() as db:
            record = await db.scalar(
                select(m.ProviderThread).filter_by(
                    iteration_id=scope, agent=agent, channel=channel
                )
            )
            if record:
                response = await self.runtime.rpc(
                    "thread/resume", {"threadId": record.thread_id, **options}
                )
            else:
                response = await self.runtime.rpc("thread/start", options)
                record = m.ProviderThread(
                    iteration_id=scope,
                    agent=agent,
                    channel=channel,
                    thread_id=response["thread"]["id"],
                )
                db.add(record)
                await db.commit()
            identifier = response["thread"]["id"]
        self.loaded[key] = (self.runtime.generation, identifier)
        return identifier

    async def execute(
        self, agent, task, context, schema, scope, channel, on_snapshot=None
    ):
        # Serializing turns also prevents provider restarts or overlapping resume RPCs from mixing queues.
        async with self.runtime.turn_lock:
            await self.runtime.start()
            if not (await self.runtime.status())["signed_in"]:
                raise CodexError("Sign in to Codex with ChatGPT first")
            thread = await self.thread(scope, agent, channel)
            queue = asyncio.Queue()
            self.runtime.queues[thread] = queue
            turn_id = None
            items = {}
            texts = {}
            usage = {}
            last_snapshot = 0.0
            try:
                started = await self.runtime.rpc(
                    "turn/start",
                    {
                        "threadId": thread,
                        "input": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {"task": task, "untrusted_data": context}
                                ),
                            }
                        ],
                        "outputSchema": schema.model_json_schema(),
                    },
                )
                turn_id = started["turn"]["id"]
                async with asyncio.timeout(self.config.codex_timeout_seconds):
                    while True:
                        msg = await queue.get()
                        method = msg["method"]
                        params = msg.get("params", {})
                        if method == "transport_error":
                            raise CodexError("Codex disconnected during turn")
                        notified_turn = params.get("turnId") or (
                            params.get("turn") or {}
                        ).get("id")
                        if notified_turn != turn_id:
                            continue
                        if method == "item/agentMessage/delta" and on_snapshot:
                            item_id = params["itemId"]
                            texts[item_id] = texts.get(item_id, "") + params["delta"]
                            if time.monotonic() - last_snapshot < 0.2:
                                continue
                            try:
                                partial = from_json(
                                    texts[item_id], allow_partial="trailing-strings"
                                )
                            except ValueError:
                                continue
                            if isinstance(partial, dict):
                                await on_snapshot(
                                    partial.get("text")
                                    or json.dumps(partial, ensure_ascii=False)
                                )
                                last_snapshot = time.monotonic()
                        elif method == "item/completed":
                            item = params["item"]
                            items[item["id"]] = item
                        elif method == "thread/tokenUsage/updated":
                            usage = params.get("tokenUsage", {}).get("last", {})
                        elif method == "turn/completed":
                            turn = params["turn"]
                            if turn["status"] != "completed":
                                raise CodexError(
                                    "Codex turn failed or was interrupted; check account limits and model access"
                                )
                            for item in turn.get("items", []):
                                items[item["id"]] = item
                            break
                final = [
                    i["text"]
                    for i in items.values()
                    if i["type"] == "agentMessage" and i.get("phase") != "commentary"
                ]
                if not final:
                    raise CodexError("Codex returned no final structured output")
                data = schema.model_validate_json(final[-1]).model_dump(mode="json")
                if on_snapshot:
                    await on_snapshot(
                        data.get("text") or json.dumps(data, ensure_ascii=False)
                    )
                return Result(
                    data, usage.get("inputTokens", 0), usage.get("outputTokens", 0)
                ), list(items.values())
            except BaseException:
                if turn_id:
                    try:
                        await self.runtime.rpc(
                            "turn/interrupt", {"threadId": thread, "turnId": turn_id}
                        )
                    except Exception:
                        pass
                raise
            finally:
                self.runtime.queues.pop(thread, None)

    async def generate(
        self, agent, task, context, schema, on_snapshot=None, scope=None
    ):
        channel = "audit" if "independent evidence audit" in task else "agent"
        result, _ = await self.execute(
            agent, task, context, schema, scope, channel, on_snapshot
        )
        return result

    async def research(self, topics, scope=None):
        result, items = await self.execute(
            "resume",
            "Research these generic topics with web search. Open each cited source with the web tool. Return only actual consulted HTTPS sources; no personal history.",
            {"topics": topics},
            CodexResearchResult,
            scope,
            "research",
        )
        consulted = set()
        calls = 0

        def collect(value):
            if isinstance(value, dict):
                url = value.get("url")
                if isinstance(url, str) and urlsplit(url).scheme == "https":
                    consulted.add(url)
                for v in value.values():
                    collect(v)
            elif isinstance(value, list):
                for v in value:
                    collect(v)

        for item in items:
            if item["type"] == "webSearch":
                calls += 1
                collect(item.get("action"))
                collect(item.get("results"))
        result.data["sources"] = [
            s for s in result.data["sources"] if s["url"] in consulted
        ]
        result.search_calls = calls
        return result
