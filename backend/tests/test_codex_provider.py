"""Codex protocol simulator only in tests. No subscription usage or real login."""

import asyncio
import json
from sqlalchemy import select
from app import schemas as s, models as m, main
from app.agents import PROMPTS
from app.codex_provider import CodexProvider
from tests.provider import TestProvider
from tests.test_workflow import upload, wait


class ProtocolRuntime:
    available = True
    generation = 1
    workspace = "/tmp/test-codex-workspace"

    def __init__(self):
        self.turn_lock = asyncio.Lock()
        self.queues = {}
        self.calls = []
        self.threads = {}
        self.provider = TestProvider()
        self.login = None
        self.signed_in = True

    async def start(self):
        pass

    async def status(self):
        return {
            "available": True,
            "signed_in": self.signed_in,
            "pending_login": self.login,
            "error": None,
        }

    async def begin_login(self):
        self.login = {
            "loginId": "login1",
            "userCode": "TEST-CODE",
            "verificationUrl": "https://auth.openai.com/codex/device",
        }
        return self.login

    async def logout(self):
        self.signed_in = False
        self.login = None

    async def close(self):
        pass

    async def rpc(self, method, params=None):
        self.calls.append((method, params))
        if method in {"thread/start", "thread/resume"}:
            tid = params.get("threadId") or f"thread-{len(self.threads) + 1}"
            self.threads[tid] = params
            return {"thread": {"id": tid}}
        if method == "turn/start":
            tid = params["threadId"]
            thread = self.threads[tid]
            payload = json.loads(params["input"][0]["text"])
            title = params["outputSchema"]["title"]
            schema = getattr(s, title)
            if schema == s.CodexResearchResult:
                data = {
                    "text": "Consulted official docs",
                    "sources": [
                        {
                            "title": "Python",
                            "url": "https://docs.python.org/3/library/asyncio.html",
                        },
                        {
                            "title": "Fabricated",
                            "url": "https://unconsulted.example/fake",
                        },
                    ],
                }
            else:
                agent = next(
                    agent
                    for agent, prompt in PROMPTS.items()
                    if prompt == thread["developerInstructions"]
                )
                data = (
                    await self.provider.generate(
                        agent, payload["task"], payload["untrusted_data"], schema
                    )
                ).data
            messages = []
            if schema == s.Answer:
                messages.append(
                    {
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": tid,
                            "turnId": "turn1",
                            "itemId": "answer",
                            "delta": json.dumps(data),
                        },
                    }
                )
            items = [
                {
                    "id": "answer",
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": json.dumps(data),
                }
            ]
            if schema == s.CodexResearchResult:
                items.append(
                    {
                        "id": "search",
                        "type": "webSearch",
                        "action": {
                            "type": "openPage",
                            "url": "https://docs.python.org/3/library/asyncio.html",
                        },
                    }
                )
            messages += [
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": tid,
                        "turnId": "turn1",
                        "tokenUsage": {
                            "last": {"inputTokens": 100, "outputTokens": 50}
                        },
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": tid,
                        "turn": {"id": "turn1", "status": "completed", "items": items},
                    },
                },
            ]
            for msg in messages:
                await self.queues[tid].put(msg)
            return {"turn": {"id": "turn1"}}
        if method == "turn/interrupt":
            return {}
        raise AssertionError(method)


async def test_codex_full_cycle_separate_threads_research_isolation_and_resume(
    env, monkeypatch
):
    c, factory, runner, _ = env
    runtime = ProtocolRuntime()
    monkeypatch.setattr(main, "codex", runtime)
    runner.provider = CodexProvider(runner.config, runtime, factory)
    rid = (await upload(c))["id"]
    result = await c.post(
        f"/resumes/{rid}/iterations",
        json={"provider_consent": True, "research_consent": True},
    )
    assert result.status_code == 201, result.text
    iid = result.json()["id"]
    await wait(runner, iid)
    detail = (await c.get(f"/iterations/{iid}")).json()
    assert detail["iteration"]["state"] == "AWAITING_APPROVAL", detail
    assert (
        detail["iteration"]["provider"] == "codex" and detail["estimated_cost"] is None
    )
    assert len(detail["transcript"]) == 20 and len(detail["sources"]) == 1
    assert (
        detail["sources"][0]["url"] == "https://docs.python.org/3/library/asyncio.html"
    )
    async with factory() as db:
        threads = list(
            (
                await db.scalars(
                    select(m.ProviderThread).where(m.ProviderThread.iteration_id == iid)
                )
            ).all()
        )
    agent_threads = [t for t in threads if t.channel == "agent"]
    assert len(agent_threads) == 3 and len({t.thread_id for t in agent_threads}) == 3
    assert {t.channel for t in threads} == {"agent", "audit", "research"}
    research_thread = next(t.thread_id for t in threads if t.channel == "research")
    for method, params in runtime.calls:
        if method == "thread/start":
            assert (
                params["sandbox"] == "read-only" and params["approvalPolicy"] == "never"
            )
        if method == "turn/start" and params["threadId"] == research_thread:
            assert json.loads(params["input"][0]["text"])["untrusted_data"] == {
                "topics": ["validation methods"]
            }
    assert runtime.threads[research_thread]["config"]["web_search"] == "live"
    assert all(
        runtime.threads[t.thread_id]["config"]["web_search"] == "disabled"
        for t in agent_threads
    )
    # Reconstruct the adapter and resume from the persisted thread ID.
    fresh = CodexProvider(runner.config, runtime, factory)
    result = await fresh.generate(
        "interviewee", "Question 1 answer", {"claims": []}, s.Answer, scope=iid
    )
    assert result.data["text"]
    assert any(
        method == "thread/resume"
        and p["threadId"]
        == next(t.thread_id for t in threads if t.agent == "interviewee")
        for method, p in runtime.calls
    )


async def test_provider_selection_login_and_origin_controls(env, monkeypatch):
    c, factory, runner, p = env
    runtime = ProtocolRuntime()
    runtime.signed_in = False
    monkeypatch.setattr(main, "codex", runtime)
    assert (
        await c.post("/provider/select", json={"provider": "codex"})
    ).status_code == 409
    assert (
        await c.post(
            "/provider/codex/login", headers={"Origin": "https://evil.example"}
        )
    ).status_code == 403
    r = await c.post("/provider/codex/login")
    assert (
        r.status_code == 200
        and r.json()["codex"]["pending_login"]["userCode"] == "TEST-CODE"
    )
    runtime.signed_in = True
    runtime.login = None
    r = await c.post("/provider/select", json={"provider": "codex"})
    assert (
        r.status_code == 200
        and r.json()["configured"]
        and r.json()["provider"] == "codex"
    )
    r = await c.post("/provider/codex/logout")
    assert r.status_code == 200 and not r.json()["configured"]
    r = await c.post("/provider/select", json={"provider": "openai"})
    assert r.status_code == 200 and r.json()["provider"] == "openai"
    await runner.provider.client.close()


async def test_codex_timeout_interrupts_turn_and_wrong_provider_blocks_recovery(
    env, monkeypatch
):
    import pytest
    from app.codex_runtime import CodexError

    c, factory, runner, _ = env
    runtime = ProtocolRuntime()
    rid = (await upload(c))["id"]
    detail = (await c.get(f"/resumes/{rid}")).json()
    async with factory() as db:
        iteration = m.Iteration(
            resume_id=rid,
            version_id=detail["resume"]["current_version_id"],
            number=1,
            state="INTERVIEWING",
            provider="codex",
            paused=True,
        )
        db.add(iteration)
        await db.commit()
        iid = iteration.id
    assert (await c.post(f"/iterations/{iid}/resume")).status_code == 409
    original = runtime.rpc

    async def hanging(method, params=None):
        if method == "turn/start":
            return {"turn": {"id": "hung-turn"}}
        return await original(method, params)

    runtime.rpc = hanging
    adapter = CodexProvider(
        runner.config.model_copy(update={"codex_timeout_seconds": 0.01}),
        runtime,
        factory,
    )
    with pytest.raises(TimeoutError):
        await adapter.generate("interviewee", "Answer", {}, s.Answer, scope=iid)
    assert (
        "turn/interrupt",
        {"threadId": "thread-1", "turnId": "hung-turn"},
    ) in runtime.calls
    runtime.signed_in = False
    with pytest.raises(CodexError):
        await adapter.generate("interviewee", "Answer", {}, s.Answer, scope=iid)
