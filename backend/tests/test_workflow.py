import asyncio
from io import BytesIO
from types import SimpleNamespace
import pytest
from app import models as m, schemas as s
from app.evidence import check_edit, metric_changes
from app.parsing import parse_resume, MAX_UPLOAD


async def upload(c, **data):
    r = await c.post(
        "/resumes",
        data={"target_role": "Product Manager", **data},
        files={
            "file": (
                "seed.md",
                b"Led product planning\nCollaborated with engineering",
                "text/markdown",
            )
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def wait(runner, iid):
    await asyncio.wait_for(runner.tasks[iid], 30)


async def test_full_workflow_approval_exports_sse(env):
    c, db, runner, p = env
    r = await upload(c, job_description="Own discovery and strategy")
    rid = r["id"]
    assert (
        await c.post(
            f"/resumes/{rid}/confirm",
            json={
                "response": "Led customer discovery and collaborated with engineering"
            },
        )
    ).status_code == 201
    started = await c.post(
        f"/resumes/{rid}/iterations",
        json={"provider_consent": True, "research_consent": True},
    )
    assert started.status_code == 201, started.text
    iid = started.json()["id"]
    await wait(runner, iid)
    run = (await c.get(f"/iterations/{iid}")).json()
    assert run["iteration"]["state"] == "AWAITING_APPROVAL", run
    assert len([t for t in run["transcript"] if not t["question"]["followup"]]) == 10
    assert len([t for t in run["transcript"] if t["question"]["followup"]]) == 10
    assert all(
        t["answer"]["actor"] == "simulated" and len(t["evaluation"]["scores"]) == 7
        for t in run["transcript"]
    )
    assert len(run["sources"]) == len(run["findings"]) == 1 and run["tokens"] > 0
    detail = (await c.get(f"/resumes/{rid}")).json()
    assert (
        detail["resume"]["original_text"]
        == "Led product planning\nCollaborated with engineering"
    )
    assert (
        len(detail["versions"]) == 2
        and "customer discovery" in detail["versions"][-1]["text"]
    )
    assert len(detail["iterations"]) == 1
    for agent, task, ctx in p.calls:
        if "target_role" in ctx:
            assert ctx["target_role"] == "Product Manager"
        if task == "research":
            assert set(ctx) == {"topics"}
    stream = await c.get(f"/iterations/{iid}/events")
    assert "approval_required" in stream.text
    ids = [
        int(line[4:]) for line in stream.text.splitlines() if line.startswith("id: ")
    ]
    replay = await c.get(
        f"/iterations/{iid}/events", headers={"Last-Event-ID": str(ids[-1])}
    )
    assert "approval_required" not in replay.text
    assert (
        await c.post(f"/resumes/{rid}/iterations", json={"provider_consent": True})
    ).status_code == 409
    nxt = await c.post(f"/iterations/{iid}/next", json={"provider_consent": True})
    assert nxt.status_code == 201 and nxt.json()["number"] == 2
    await wait(runner, nxt.json()["id"])
    assert (
        await c.post(f"/iterations/{iid}/next", json={"provider_consent": True})
    ).status_code == 409
    vid = detail["versions"][-1]["id"]
    for fmt, magic in [("md", b"Led"), ("pdf", b"%PDF"), ("docx", b"PK")]:
        response = await c.get(f"/versions/{vid}/export/{fmt}")
        assert response.status_code == 200 and response.content.startswith(magic)


async def test_pause_resume_cancel_recovery(env):
    c, factory, runner, p = env
    rid = (await upload(c))["id"]
    p.gate = asyncio.Event()
    response = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    iid = response.json()["id"]
    await p.entered.wait()
    assert (await c.post(f"/iterations/{iid}/pause")).status_code == 200
    p.gate.set()
    await asyncio.sleep(0.15)
    count = len(p.calls)
    await asyncio.sleep(0.3)
    assert len(p.calls) == count
    await c.post(f"/iterations/{iid}/resume")
    await wait(runner, iid)
    await c.post(f"/iterations/{iid}/stop")
    p.entered.clear()
    p.gate = asyncio.Event()
    response = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    iid = response.json()["id"]
    await p.entered.wait()
    await runner.shutdown()
    await runner.recover()
    async with factory() as db:
        assert (await db.get(m.Iteration, iid)).paused
    p.gate.set()
    await c.post(f"/iterations/{iid}/resume")
    await wait(runner, iid)
    await c.post(f"/iterations/{iid}/stop")
    p.entered.clear()
    p.gate = asyncio.Event()
    response = await c.post(
        f"/resumes/{rid}/iterations", json={"provider_consent": True}
    )
    iid = response.json()["id"]
    await p.entered.wait()
    await c.post(f"/iterations/{iid}/cancel")
    p.gate.set()
    await wait(runner, iid)
    assert (await c.get(f"/iterations/{iid}")).json()["iteration"][
        "state"
    ] == "CANCELLED"


async def test_failure_retry_errors_manual_edits(env):
    c, factory, runner, p = env
    rid = (await upload(c))["id"]
    assert (await c.post(f"/resumes/{rid}/iterations", json={})).status_code == 422
    p.fail = True
    r = await c.post(f"/resumes/{rid}/iterations", json={"provider_consent": True})
    iid = r.json()["id"]
    await wait(runner, iid)
    assert (await c.get(f"/iterations/{iid}")).json()["iteration"]["state"] == "FAILED"
    p.fail = False
    await c.post(f"/iterations/{iid}/retry")
    await wait(runner, iid)
    assert not (await c.get(f"/iterations/{iid}")).json()["sources"]
    await c.post(f"/iterations/{iid}/stop")
    r = await c.put(
        f"/resumes/{rid}/versions",
        json={"text": "Corrected resume", "reason": "Correction"},
    )
    assert r.status_code == 201 and not r.json()["submission_ready"]
    assert (await c.get(f"/resumes/{rid}")).json()["claims"][0][
        "status"
    ] == "UNVERIFIED"
    assert (await c.get("/resumes/missing")).status_code == 404
    assert (
        await c.post("/resumes", files={"file": ("x.exe", b"bad")})
    ).status_code == 422
    assert (
        await c.post(
            "/resumes",
            data={"job_description": "Operations coordinator"},
            files={"file": ("x.md", b"Coordinated schedules")},
        )
    ).status_code == 201


@pytest.mark.parametrize(
    "status,kind,text,ok",
    [
        ("PUBLIC_CONTEXT", "research", "Improved throughput", False),
        ("UNVERIFIED", "candidate_note", "Improved throughput", False),
        (
            "CANDIDATE_CONFIRMED",
            "candidate_confirmation",
            "Improved throughput by 25%",
            False,
        ),
        (
            "CANDIDATE_CONFIRMED",
            "candidate_confirmation",
            "Implemented asynchronous validation",
            True,
        ),
        ("VERIFIED", "measurement", "Reduced failure rate from 5% to 2%", True),
    ],
)
def test_evidence_guard(status, kind, text, ok):
    e = s.Edit(
        claim_id="c",
        previous_text="Worked on evaluation",
        new_text=text,
        reason="Detail",
        evidence_ids=["e"],
    )
    evidence = {"e": SimpleNamespace(status=status, kind=kind, text=text)}
    assert (
        check_edit(
            e, SimpleNamespace(text=e.previous_text), evidence, {"verdict": "PASS"}
        )[0]
        is ok
    )
    assert not check_edit(
        e, SimpleNamespace(text=e.previous_text), evidence, {"verdict": "HOLD"}
    )[0]


def test_metrics_and_schemas():
    change = metric_changes(0.05, 0.02)
    assert change["percentage_point_change"] == pytest.approx(-3)
    assert change["relative_percentage_change"] == pytest.approx(-60)
    assert metric_changes(0, 1)["relative_percentage_change"] is None
    with pytest.raises(ValueError):
        s.Score(value=11, reason="Invalid")
    with pytest.raises(ValueError):
        s.Question(text="Q", claim_ids=[], difficulty="senior", hidden_reasoning="no")


def test_safe_parsing():
    assert parse_resume("x.md", b"# Candidate") == "# Candidate"
    from docx import Document

    doc = Document()
    doc.add_paragraph("Candidate")
    out = BytesIO()
    doc.save(out)
    assert parse_resume("x.docx", out.getvalue()) == "Candidate"
    for name, data in [
        ("x.md", b""),
        ("x.md", b"x" * (MAX_UPLOAD + 1)),
        ("x.exe", b"text"),
        ("x.docx", b"invalid"),
    ]:
        with pytest.raises(Exception):
            parse_resume(name, data)


async def test_metric_artifact_review_is_explicit(env):
    c, factory, runner, p = env
    rid = (await upload(c))["id"]
    payload = dict(
        project_name="Evaluation",
        metric_name="Evaluation-job failure rate",
        metric_definition="failed/total jobs",
        numerator=2,
        denominator=100,
        baseline_value=0.05,
        final_value=0.02,
        unit="proportion",
        sample_size=100,
        observation_window="One week",
        workload_description="Fixed regression set",
        hardware_configuration="Recorded test host",
        concurrency=1,
        model_configuration="Pinned model",
        measurement_method="Count persisted terminal outcomes",
        source_reference="Internal report R1",
        limitations="Small sample; no causal claim",
        relationship="correlation",
    )
    r = await c.post(f"/resumes/{rid}/metrics", json=payload)
    assert r.status_code == 201
    mid = r.json()["metric"]["id"]
    assert r.json()["metric"]["evidence_status"] == "UNVERIFIED"
    assert r.json()["changes"]["percentage_point_change"] == pytest.approx(-3)
    assert (
        await c.post(
            f"/metrics/{mid}/review",
            json={
                "reviewed_direct_measurement": False,
                "review_note": "Only a recollection",
                "supported_statement": "Reduced failure rate",
            },
        )
    ).status_code == 422
    r = await c.post(
        f"/metrics/{mid}/review",
        json={
            "reviewed_direct_measurement": True,
            "review_note": "Reviewed report R1 with the baseline and final counts",
            "supported_statement": "Observed failure rate of 2% across 100 test jobs",
        },
    )
    assert (
        r.status_code == 200
        and r.json()["kind"] == "measurement"
        and r.json()["status"] == "VERIFIED"
    )
    assert (await c.get(f"/resumes/{rid}")).json()["metrics"][0][
        "evidence_status"
    ] == "VERIFIED"


async def test_no_attributable_research_preserves_approval_gate(env):
    from app.agents import Result

    c, factory, runner, p = env

    async def empty(topics):
        return Result(
            {"text": "No relevant attributable sources", "sources": []}, 10, 10, 1
        )

    p.research = empty
    rid = (await upload(c))["id"]
    result = await c.post(
        f"/resumes/{rid}/iterations",
        json={"provider_consent": True, "research_consent": True},
    )
    iid = result.json()["id"]
    await wait(runner, iid)
    state = (await c.get(f"/iterations/{iid}")).json()
    assert state["iteration"]["state"] == "AWAITING_APPROVAL" and not state["sources"]
    assert len((await c.get(f"/resumes/{rid}")).json()["versions"]) == 1
