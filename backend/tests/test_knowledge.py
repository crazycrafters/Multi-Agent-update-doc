import asyncio
import json
import httpx
import pytest
from sqlalchemy import select
from openai import AsyncOpenAI
from app import models as m
from tests.test_workflow import wait


async def profile(c, name):
    r = await c.post(
        "/profiles",
        json={
            "name": name,
            "target_role": name + " Engineer",
            "job_description": "Durable systems",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def seed(c, pid):
    r = await c.post(
        "/resumes",
        data={"profile_id": pid},
        files={"file": ("seed.md", b"Implemented pipeline validation")},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def note(c, pid, content, status="CANDIDATE_CONFIRMED", kind="personal"):
    r = await c.post(
        f"/profiles/{pid}/knowledge",
        json={
            "title": "Pipeline dossier",
            "project": "Evaluation",
            "source": "Candidate-provided project notes",
            "content": content,
            "status": status,
            "kind": kind,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_profile_knowledge_isolation_versioning_archive_and_export(env):
    c, factory, runner, p = env
    a = await profile(c, "Alpha")
    b = await profile(c, "Beta")
    doc = await note(c, a, "Alpha pipeline uses durable retries. I owned validation.")
    other = await note(c, b, "Beta pipeline SECRET_BETA uses a different retry design.")
    found = (
        await c.post(
            f"/profiles/{a}/knowledge/search", json={"query": "pipeline retries"}
        )
    ).json()
    assert found["results"] and all(
        "SECRET_BETA" not in x["text"] for x in found["results"]
    )
    metadata = await c.post(
        f"/profiles/{a}/knowledge/search", json={"query": "dossier"}
    )
    assert metadata.json()["results"][0]["document_id"] == doc["id"]
    assert (
        await c.post(f"/profiles/{a}/knowledge/{other['id']}/archive")
    ).status_code == 404
    revised = await c.put(
        f"/profiles/{a}/knowledge/{doc['id']}",
        json={
            "title": "Corrected dossier",
            "project": "Evaluation",
            "source": "Corrected notes",
            "content": "Alpha pipeline uses bounded backoff and validation.",
            "kind": "personal",
            "status": "CANDIDATE_CONFIRMED",
        },
    )
    assert revised.status_code == 200 and revised.json()["version"] == 2
    records = (await c.get(f"/profiles/{a}/knowledge")).json()
    assert len(records) == 2 and sum(d["active"] for d in records) == 1
    exported = (await c.get(f"/profiles/{a}/knowledge/export")).json()
    assert exported["schema_version"] == 1 and len(exported["documents"]) == 1
    assert all(
        "embedding" not in x for x in exported["chunks"]
    ) and "SECRET_BETA" not in json.dumps(exported)
    md = await c.get(f"/profiles/{a}/knowledge/export?format=md")
    assert "CANDIDATE_CONFIRMED" in md.text and "SECRET_BETA" not in md.text
    await c.post(f"/profiles/{a}/knowledge/{revised.json()['id']}/archive")
    assert not (
        await c.post(f"/profiles/{a}/knowledge/search", json={"query": "pipeline"})
    ).json()["results"]
    ref = await note(c, a, "Public pipeline documentation", kind="reference")
    assert ref["status"] == "PUBLIC_CONTEXT"
    assert (
        await c.post(
            f"/profiles/{a}/knowledge",
            json={
                "title": "No",
                "source": "x",
                "content": "x",
                "kind": "personal",
                "status": "VERIFIED",
            },
        )
    ).status_code == 422


async def test_pgvector_embedding_and_hybrid_search_are_scoped_and_consented(
    env, monkeypatch
):
    c, factory, runner, p = env
    a = await profile(c, "Alpha")
    b = await profile(c, "Beta")
    doc = await note(c, a, "I owned async validation with bounded retries.")
    await note(c, b, "SECRET_BETA unrelated source")
    assert (
        await c.post(
            f"/profiles/{a}/knowledge/{doc['id']}/embed", json={"consent": False}
        )
    ).status_code == 422
    assert (
        await c.post(
            f"/profiles/{a}/knowledge/{doc['id']}/embed", json={"consent": True}
        )
    ).status_code == 503
    runner.config = runner.config.model_copy(
        update={"openai_api_key": "test-embedding-key"}
    )
    requests = []

    async def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert (
            payload["model"] == "text-embedding-3-small"
            and payload["dimensions"] == 1536
        )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        "embedding": [1.0] + [0.0] * 1535,
                    }
                    for i in range(len(payload["input"]))
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 12, "total_tokens": 12},
            },
        )

    def client(**kwargs):
        return AsyncOpenAI(
            api_key="test-embedding-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("app.knowledge.AsyncOpenAI", client)
    response = await c.post(
        f"/profiles/{a}/knowledge/{doc['id']}/embed", json={"consent": True}
    )
    assert response.status_code == 200, response.text
    repeated = await c.post(
        f"/profiles/{a}/knowledge/{doc['id']}/embed", json={"consent": True}
    )
    assert repeated.json()["indexed"] == 0 and len(requests) == 1
    found = await c.post(
        f"/profiles/{a}/knowledge/search",
        json={"query": "validation", "semantic": True, "embedding_consent": True},
    )
    assert found.status_code == 200 and found.json()["method"] == "hybrid"
    assert found.json()["results"][0]["document_id"] == doc["id"]
    assert all("SECRET_BETA" not in json.dumps(req) for req in requests)
    assert (await c.get(f"/profiles/{a}/knowledge")).json()[0]["embedded_chunks"] > 0
    usage = (await c.get("/usage")).json()
    assert usage["tokens"] >= 24 and usage["api"]["remaining_budget_usd"] is None


async def test_batched_rag_run_settings_snapshot_strategies_and_citations(env):
    c, factory, runner, p = env
    a = await profile(c, "Alpha")
    b = await profile(c, "Beta")
    rid = await seed(c, a)
    doc = await note(
        c,
        a,
        "Ownership validation: I implemented pipeline validation and bounded retries for Alpha Engineer.",
    )
    await note(c, b, "SECRET_BETA ownership evidence")
    cfg = (await c.get("/settings")).json()
    cfg["workflow"].update(
        question_count=2, followups=False, initial_draft=False, research=False
    )
    cfg["strategies"]["interviewee"] = (
        "Acknowledge unknown history and focus on validation."
    )
    assert (await c.put("/settings", json=cfg)).status_code == 200
    started = await c.post(
        f"/resumes/{rid}/iterations",
        json={"provider_consent": True, "iteration_count": 2},
    )
    assert started.status_code == 201, started.text
    first = started.json()["id"]
    await wait(runner, first)
    detail = (await c.get(f"/resumes/{rid}")).json()
    assert len(detail["iterations"]) == 2
    last = detail["iterations"][-1]
    await wait(runner, last["id"])
    run = (await c.get(f"/iterations/{last['id']}")).json()
    assert run["iteration"]["state"] == "AWAITING_APPROVAL"
    assert (
        run["iteration"]["run_step"] == 2
        and run["iteration"]["run_id"] == started.json()["run_id"]
    )
    assert (
        len(run["transcript"]) == 2
        and 2 <= len(run["iteration"]["checkpoint"]["strategies"]) <= 4
    )
    for agent, task, context in p.calls:
        assert "SECRET_BETA" not in json.dumps(context)
        assert "settings" not in context.get("checkpoint", {})
        assert "api_budget_usd" not in json.dumps(context)

        if agent == "interviewee" and "current_question" in context:
            assert (
                context["working_strategy"] == cfg["strategies"]["interviewee"]
                and context["knowledge"]
            )
    assert any(t["answer"]["knowledge_ids"] for t in run["transcript"])
    stream = await c.get(f"/iterations/{last['id']}/events")
    assert "knowledge_retrieved" in stream.text and "strategy_choices" in stream.text
    assert (
        await c.post(
            f"/iterations/{last['id']}/strategies/select",
            json={"strategy_id": "invalid"},
        )
    ).status_code == 422
    choice = run["iteration"]["checkpoint"]["strategies"][0]["id"]
    assert (
        await c.post(
            f"/iterations/{last['id']}/strategies/select", json={"strategy_id": choice}
        )
    ).status_code == 200
    await asyncio.sleep(0.01)
    await wait(runner, last["id"])
    selected = (await c.get(f"/iterations/{last['id']}")).json()["iteration"]
    assert (
        selected["state"] == "AWAITING_APPROVAL"
        and selected["checkpoint"]["selected_strategy"]["id"] == choice
    )


async def test_budget_is_not_fabricated_balance_and_invalid_citations_fail(env):
    c, factory, runner, p = env
    a = await profile(c, "Alpha")
    rid = await seed(c, a)
    cfg = (await c.get("/settings")).json()
    cfg.update(api_budget_usd=0, input_usd_per_million=1, output_usd_per_million=2)
    await c.put("/settings", json=cfg)
    started = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    await wait(runner, started.json()["id"])
    assert not p.calls
    assert (await c.get(f"/iterations/{started.json()['id']}")).json()["iteration"][
        "state"
    ] == "FAILED"
    usage = (await c.get("/usage")).json()
    assert (
        usage["api"]["remaining_budget_usd"] == 0
        and usage["api"]["account_balance_available"] is False
    )


async def test_unknown_rag_citations_fail_and_codex_limits_are_sanitized(
    env, monkeypatch
):
    from app import main, schemas as s

    c, factory, runner, p = env
    pid = await profile(c, "Alpha")
    rid = await seed(c, pid)
    original = p.generate

    async def bad_citation(agent, task, context, schema, **kwargs):
        result = await original(agent, task, context, schema, **kwargs)
        if schema is s.Answer:
            result.data["knowledge_ids"] = ["foreign-profile-chunk"]
        return result

    p.generate = bad_citation
    started = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    await wait(runner, started.json()["id"])
    assert (await c.get(f"/iterations/{started.json()['id']}")).json()["iteration"][
        "state"
    ] == "FAILED"

    class RateRuntime:
        process = True

        async def rpc(self, method):
            assert method == "account/rateLimits/read"
            return {
                "accountId": "private-account",
                "rateLimits": {
                    "primary": {
                        "usedPercent": 60,
                        "windowDurationMins": 300,
                        "resetsAt": 1900000000,
                        "secret": "never-return",
                    },
                    "secondary": {"usedPercent": 40},
                },
            }

    monkeypatch.setattr(main, "codex", RateRuntime())
    p.kind = "codex"
    usage = await c.get("/usage")
    assert (
        usage.status_code == 200
        and usage.json()["codex"]["limits"]["primary"]["usedPercent"] == 60
    )
    assert "private-account" not in usage.text and "never-return" not in usage.text


async def test_contradicted_profile_knowledge_holds_changes_and_references_never_become_evidence(
    env,
):
    c, factory, runner, p = env
    pid = await profile(c, "Alpha")
    rid = await seed(c, pid)
    await note(c, pid, "Implemented pipeline validation with bounded retries.")
    await note(
        c,
        pid,
        "The historical ownership is disputed and must be resolved.",
        status="CONTRADICTED",
    )
    await note(
        c,
        pid,
        "Published pipeline architecture reference with public benchmarks.",
        kind="reference",
    )
    cfg = (await c.get("/settings")).json()
    cfg["workflow"].update(question_count=1, followups=False, research=False)
    await c.put("/settings", json=cfg)
    started = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    iid = started.json()["id"]
    await wait(runner, iid)
    detail = (await c.get(f"/resumes/{rid}")).json()
    assert len(detail["versions"]) == 1 and not detail["revisions"]
    assert all(e["status"] != "PUBLIC_CONTEXT" for e in detail["evidence"])
    events = await c.get(f"/iterations/{iid}/events")
    assert "Resolve contradicted personal knowledge" in events.text
