import json
import httpx
from openai import AsyncOpenAI
from app.agents import OpenAIProvider
from app.config import Settings
from app.schemas import Question


async def test_real_sdk_structured_output_and_web_search_transport():
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        text = (
            json.dumps(
                {
                    "text": "Explain your actual contribution",
                    "claim_ids": [],
                    "difficulty": "target-role",
                }
            )
            if "tools" not in body
            else "Public guidance"
        )
        output = [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": []
                        if "tools" not in body
                        else [
                            {
                                "type": "url_citation",
                                "url": "https://docs.python.org/3/",
                                "title": "Python docs",
                                "start_index": 0,
                                "end_index": 10,
                            }
                        ],
                    }
                ],
            }
        ]
        if "tools" in body:
            output.insert(
                0,
                {
                    "id": "ws_test",
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "validation",
                        "sources": [
                            {"type": "url", "url": "https://docs.python.org/3/"}
                        ],
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4.1-mini",
                "status": "completed",
                "output": output,
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            },
        )

    provider = OpenAIProvider(Settings(openai_api_key="test-not-a-real-key"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider.client = AsyncOpenAI(api_key="test-not-a-real-key", http_client=client)
        result = await provider.generate(
            "interviewer", "Ask one question", {"target_role": "Nurse"}, Question
        )
        assert (
            result.data["text"] == "Explain your actual contribution"
            and result.input_tokens == 10
        )
        result = await provider.research(["validation"])
        assert (
            result.search_calls == 1
            and result.data["sources"][0]["url"] == "https://docs.python.org/3/"
        )
        assert requests[0]["store"] is False and requests[0]["text"]["format"]["strict"]
        assert requests[1]["tools"] == [{"type": "web_search"}]
        assert "Nurse" not in requests[1]["input"]


async def test_official_sdk_answer_stream_snapshots():
    from app.schemas import Answer

    payload = {
        "text": "I implemented only the confirmed contribution.",
        "limitations": ["No measurement artifact"],
        "claim_ids": [],
    }
    text = json.dumps(payload)
    part = {"type": "output_text", "text": text, "annotations": []}
    message = {
        "id": "msg_stream",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [part],
    }
    base = {
        "id": "resp_stream",
        "object": "response",
        "created_at": 1,
        "model": "gpt-4.1-mini",
        "status": "in_progress",
        "output": [],
    }
    events = [
        {"type": "response.created", "response": base},
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**message, "status": "in_progress", "content": []},
        },
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "part": {"type": "output_text", "text": "", "annotations": []},
        },
    ]
    for chunk in [text[:50], text[50:]]:
        events.append(
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "content_index": 0,
                "item_id": "msg_stream",
                "delta": chunk,
            }
        )
    events += [
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "text": text,
        },
        {
            "type": "response.content_part.done",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "part": part,
        },
        {"type": "response.output_item.done", "output_index": 0, "item": message},
        {
            "type": "response.completed",
            "response": {
                **base,
                "status": "completed",
                "output": [message],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            },
        },
    ]
    wire = "".join(
        "event: "
        + e["type"]
        + "\ndata: "
        + json.dumps({**e, "sequence_number": i})
        + "\n\n"
        for i, e in enumerate(events)
    )

    async def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, content=wire
        )

    provider = OpenAIProvider(Settings(openai_api_key="test-not-a-real-key"))
    snapshots = []

    async def snapshot(text):
        snapshots.append(text)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider.client = AsyncOpenAI(api_key="test-not-a-real-key", http_client=client)
        result = await provider.generate(
            "interviewee", "Question 1 answer", {}, Answer, on_snapshot=snapshot
        )
    assert (
        result.data == payload
        and snapshots[-1] == payload["text"]
        and len(snapshots) >= 2
    )
