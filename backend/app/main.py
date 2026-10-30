import asyncio
import hmac
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from io import BytesIO
from xml.sax.saxutils import escape
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from . import models as m, schemas as s
from .agents import OpenAIProvider
from .codex_runtime import CodexRuntime, CodexError
from .codex_provider import CodexProvider
from .config import settings
from .database import Session, get_db
from .workflow import Workflow, create_version, rows, public, event, TERMINAL
from .parsing import MAX_UPLOAD, parse_resume
from .evidence import metric_changes

from .logging_config import configure_logging

configure_logging()
workflow = Workflow()
codex = CodexRuntime(settings())
locks = defaultdict(asyncio.Lock)
rate = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    await workflow.recover()
    yield
    await workflow.shutdown()
    await codex.close()
    if isinstance(workflow.provider, OpenAIProvider):
        await workflow.provider.client.close()


app = FastAPI(title="AI Resume Evolution", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().cors_origin],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)


@app.middleware("http")
async def guard(request, call_next):
    token = settings().api_access_token
    if token and request.url.path != "/health":
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(token, supplied):
            return JSONResponse(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "Authentication required",
                    }
                },
                status_code=401,
            )
    if request.method in {"POST", "PUT"}:
        length = request.headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > MAX_UPLOAD + 65536):
            return JSONResponse(
                {
                    "error": {
                        "code": "upload_too_large",
                        "message": "Request exceeds limit",
                    }
                },
                status_code=413,
            )
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        q = rate[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 60:
            return JSONResponse(
                {"error": {"code": "rate_limit", "message": "Try again in one minute"}},
                status_code=429,
            )
        q.append(now)
    return await call_next(request)


@app.exception_handler(HTTPException)
async def api_error(request, exc):
    return JSONResponse(
        {"error": {"code": str(exc.status_code), "message": exc.detail}},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        {
            "error": {
                "code": "validation",
                "message": "Request validation failed",
                "fields": [
                    {"location": list(e["loc"]), "message": e["msg"]}
                    for e in exc.errors()
                ],
            }
        },
        status_code=422,
    )


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse(
        {"error": {"code": "internal_error", "message": "Unexpected server error"}},
        status_code=500,
    )


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(
        {
            "error": {
                "code": "conflict",
                "message": "Concurrent change; reload and retry",
            }
        },
        status_code=409,
    )


async def need(db, cls, identifier):
    obj = await db.get(cls, identifier)
    if obj is None:
        raise HTTPException(404, "Record not found")
    return obj


async def editable(db, resume_id):
    active = await db.scalar(
        select(m.Iteration).where(
            m.Iteration.resume_id == resume_id,
            m.Iteration.state.not_in({"COMPLETED", "CANCELLED"}),
        )
    )
    if active:
        raise HTTPException(
            409,
            "Stop or cancel the current iteration before changing the resume or evidence",
        )


@app.get("/health")
async def health(db=Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "provider_configured": (await provider_status())["configured"],
    }


@app.get("/resumes")
async def resumes(db=Depends(get_db)):
    return [public(x) for x in await rows(db, m.Resume)]


@app.post("/resumes", status_code=201)
async def upload(
    file: UploadFile = File(...),
    target_role: str = Form(""),
    job_description: str = Form(""),
    db=Depends(get_db),
):
    if not target_role.strip() and not job_description.strip():
        raise HTTPException(422, "Provide a target role or job description")
    if len(target_role) > 500 or len(job_description) > 30000:
        raise HTTPException(422, "Target context exceeds limits")
    data = await file.read(MAX_UPLOAD + 1)
    try:
        content = await asyncio.to_thread(parse_resume, file.filename or "", data)
    except Exception:
        raise HTTPException(
            422,
            "Unable to parse upload. Use readable UTF-8 text/Markdown, PDF, or DOCX up to 2 MB.",
        )
    user = await db.scalar(select(m.User).limit(1))
    if not user:
        user = m.User()
        db.add(user)
        await db.flush()
    resume = m.Resume(
        user_id=user.id,
        title=(file.filename or "Resume")[:200],
        original_text=content,
        target_role=target_role.strip() or "Role described in job description",
        job_description=job_description.strip(),
    )
    db.add(resume)
    await db.flush()
    await create_version(
        db, resume, content, "Original uploaded seed; claims not independently verified"
    )
    await db.commit()
    return public(resume)


@app.get("/resumes/{rid}")
async def detail(rid: str, db=Depends(get_db)):
    resume = await need(db, m.Resume, rid)
    return {
        "resume": public(resume),
        "versions": [public(x) for x in await rows(db, m.ResumeVersion, resume_id=rid)],
        "iterations": [public(x) for x in await rows(db, m.Iteration, resume_id=rid)],
        "claims": [
            public(x)
            for x in await rows(db, m.Claim, version_id=resume.current_version_id)
        ],
        "evidence": [
            public(x) for x in await rows(db, m.EvidenceRecord, resume_id=rid)
        ],
        "confirmations": [
            public(x) for x in await rows(db, m.CandidateConfirmation, resume_id=rid)
        ],
        "revisions": [
            public(x)
            for x in (
                await db.scalars(
                    select(m.Revision)
                    .join(m.ResumeVersion)
                    .where(m.ResumeVersion.resume_id == rid)
                )
            ).all()
        ],
        "metrics": [
            public(x)
            for x in (
                await db.scalars(
                    select(m.MetricEvidence)
                    .join(m.Project)
                    .where(m.Project.resume_id == rid)
                )
            ).all()
        ],
    }


@app.put("/resumes/{rid}/versions", status_code=201)
async def manual_edit(rid: str, body: s.EditRequest, db=Depends(get_db)):
    async with locks[rid]:
        resume = await need(db, m.Resume, rid)
        await editable(db, rid)
        old = await need(db, m.ResumeVersion, resume.current_version_id)
        if old.text == body.text:
            raise HTTPException(409, "No text changed")
        v = await create_version(db, resume, body.text, "Manual edit: " + body.reason)
        db.add(
            m.Revision(
                version_id=v.id,
                previous_text=old.text,
                new_text=v.text,
                reason=body.reason,
                evidence_ids=[],
                agent="human",
                audit={
                    "verdict": "HOLD",
                    "reason": "Manual edits are not verified evidence",
                },
            )
        )
        await db.commit()
        return public(v)


@app.post("/resumes/{rid}/evidence", status_code=201)
async def evidence(rid: str, body: s.EvidenceRequest, db=Depends(get_db)):
    async with locks[rid]:
        await need(db, m.Resume, rid)
        await editable(db, rid)
        e = m.EvidenceRecord(resume_id=rid, **body.model_dump(), status="UNVERIFIED")
        db.add(e)
        await db.commit()
        return public(e)


@app.post("/confirmations/{cid}")
async def confirm(cid: str, body: s.ConfirmRequest, db=Depends(get_db)):
    c = await need(db, m.CandidateConfirmation, cid)
    async with locks[c.resume_id]:
        await editable(db, c.resume_id)
        if c.response:
            raise HTTPException(
                409, "Already confirmed; add a correction as new evidence"
            )
        e = m.EvidenceRecord(
            resume_id=c.resume_id,
            text=body.response,
            source=f"Explicit candidate confirmation: {c.question}",
            status="CANDIDATE_CONFIRMED",
            kind="candidate_confirmation",
        )
        db.add(e)
        await db.flush()
        c.response = body.response
        c.evidence_id = e.id
        await db.commit()
        return public(c)


@app.post("/resumes/{rid}/confirm", status_code=201)
async def direct_confirm(rid: str, body: s.ConfirmRequest, db=Depends(get_db)):
    async with locks[rid]:
        await need(db, m.Resume, rid)
        await editable(db, rid)
        c = m.CandidateConfirmation(
            resume_id=rid,
            question="Explicit candidate-supplied factual confirmation",
            response=body.response,
        )
        e = m.EvidenceRecord(
            resume_id=rid,
            text=body.response,
            source="Explicit candidate confirmation",
            status="CANDIDATE_CONFIRMED",
            kind="candidate_confirmation",
        )
        db.add(e)
        await db.flush()
        c.evidence_id = e.id
        db.add(c)
        await db.commit()
        return public(e)


@app.post("/resumes/{rid}/metrics", status_code=201)
async def metrics(rid: str, body: s.MetricRequest, db=Depends(get_db)):
    async with locks[rid]:
        await need(db, m.Resume, rid)
        await editable(db, rid)
        project = await db.scalar(
            select(m.Project).where(
                m.Project.resume_id == rid, m.Project.name == body.project_name
            )
        )
        if not project:
            project = m.Project(resume_id=rid, name=body.project_name)
            db.add(project)
            await db.flush()
        record = m.MetricEvidence(
            project_id=project.id,
            **body.model_dump(exclude={"project_name"}),
            evidence_status="UNVERIFIED",
        )
        db.add(record)
        await db.commit()
        return {
            "metric": public(record),
            "changes": metric_changes(body.baseline_value, body.final_value)
            if body.baseline_value is not None
            else None,
            "warning": "Recorded unverified. Percentage points apply only to proportions. Artifacts require review.",
        }


async def start_new(db, resume, body):
    async with locks["provider_connection"]:
        return await start_new_locked(db, resume, body)


async def start_new_locked(db, resume, body):
    if not body.provider_consent:
        raise HTTPException(
            422,
            "Explicit consent to send resume/evidence to the AI provider is required",
        )
    if not workflow.config.openai_api_key and isinstance(
        workflow.provider, OpenAIProvider
    ):
        raise HTTPException(
            503, "Connect an OpenAI API key in the dashboard before starting"
        )
    if isinstance(workflow.provider, CodexProvider):
        try:
            await codex.start()
            if not (await codex.status())["signed_in"]:
                raise HTTPException(503, "Sign in to Codex first")
        except CodexError:
            raise HTTPException(
                503, "Codex unavailable; check installation and ChatGPT sign-in"
            )
    n = (
        await db.scalar(
            select(func.max(m.Iteration.number)).where(
                m.Iteration.resume_id == resume.id
            )
        )
        or 0
    )
    it = m.Iteration(
        resume_id=resume.id,
        version_id=resume.current_version_id,
        number=n + 1,
        state="RESUME_ANALYSIS",
        provider=getattr(workflow.provider, "kind", "openai"),
        provider_consent=body.provider_consent,
        research_consent=body.research_consent,
        checkpoint={},
    )
    db.add(it)
    await db.commit()
    workflow.launch(it.id)
    return public(it)


@app.post("/resumes/{rid}/iterations", status_code=201)
async def start(rid: str, body: s.StartRequest, db=Depends(get_db)):
    async with locks[rid]:
        resume = await need(db, m.Resume, rid)
        await editable(db, rid)
        return await start_new(db, resume, body)


@app.post("/iterations/{iid}/next", status_code=201)
async def approve(iid: str, body: s.StartRequest, db=Depends(get_db)):
    old = await need(db, m.Iteration, iid)
    async with locks[old.resume_id]:
        await db.refresh(old)
        if old.state != "AWAITING_APPROVAL":
            raise HTTPException(
                409, "Only an awaiting-approval iteration can be approved"
            )
        if not body.provider_consent:
            raise HTTPException(422, "Provider consent required")
        old.state = "COMPLETED"
        await event(
            db,
            iid,
            "human",
            "approved",
            {"message": "Explicit approval to start next iteration"},
        )
        resume = await need(db, m.Resume, old.resume_id)
        return await start_new(db, resume, body)


@app.post("/iterations/{iid}/{action}")
async def control(iid: str, action: str, db=Depends(get_db)):
    return await control_locked(iid, action, db)


async def control_locked(iid, action, db):
    if action not in {"pause", "resume", "cancel", "stop", "retry"}:
        raise HTTPException(404, "Unknown action")
    it = await need(db, m.Iteration, iid)
    async with locks[it.resume_id]:
        async with locks["provider_connection"]:
            await db.refresh(it)
            if action in {"resume", "retry"} and it.provider != getattr(
                workflow.provider, "kind", "openai"
            ):
                raise HTTPException(
                    409, "Select the iteration's original provider before resuming"
                )
            if action == "pause":
                if it.state in TERMINAL:
                    raise HTTPException(409, "Iteration is not running")
                it.paused = True
            elif action == "resume":
                if it.state in TERMINAL:
                    raise HTTPException(409, "Iteration is not resumable")
                it.paused = False
            elif action == "retry":
                if it.state != "FAILED":
                    raise HTTPException(409, "Only failed iterations can be retried")
                it.state = it.checkpoint.get("failed_phase", "RESUME_ANALYSIS")
                it.error = None
                it.paused = False
            elif action == "cancel":
                if it.state in {"COMPLETED", "CANCELLED"}:
                    raise HTTPException(409, "Iteration already finished")
                it.cancel_requested = True
                it.state = "CANCELLED"
            else:
                if it.state != "AWAITING_APPROVAL":
                    raise HTTPException(
                        409,
                        "Stop requires awaiting approval; use Cancel for active work",
                    )
                it.state = "COMPLETED"
            await event(
                db, iid, "human", action, {"state": it.state, "paused": it.paused}
            )
            await db.commit()
            if action in {"resume", "retry"}:
                workflow.launch(iid)
            return public(it)


@app.get("/iterations/{iid}")
async def iteration(iid: str, db=Depends(get_db)):
    it = await need(db, m.Iteration, iid)
    ctx = await workflow.context(db, it)
    executions = await rows(db, m.AgentExecution, iteration_id=iid)
    return {
        "iteration": public(it),
        "transcript": ctx["transcript"],
        "sources": [
            public(x) for x in await rows(db, m.ResearchSource, iteration_id=iid)
        ],
        "findings": [
            public(x)
            for x in (
                await db.scalars(
                    select(m.ResearchFinding)
                    .join(m.ResearchSource)
                    .where(m.ResearchSource.iteration_id == iid)
                )
            ).all()
        ],
        "executions": [public(x) for x in executions],
        "tokens": sum(x.input_tokens + x.output_tokens for x in executions),
        "estimated_cost": None
        if any(x.estimated_cost is None for x in executions)
        else sum(x.estimated_cost for x in executions),
    }


@app.get("/iterations/{iid}/events")
async def events(iid: str, request: Request, after: int = 0, db=Depends(get_db)):
    await need(db, m.Iteration, iid)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(422, "Invalid event cursor")

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            async with Session() as connection:
                records = list(
                    (
                        await connection.scalars(
                            select(m.AgentEvent)
                            .where(
                                m.AgentEvent.iteration_id == iid,
                                m.AgentEvent.id > cursor,
                            )
                            .order_by(m.AgentEvent.id)
                            .limit(100)
                        )
                    ).all()
                )
                it = await connection.get(m.Iteration, iid)
                for record in records:
                    cursor = record.id
                    yield f"id: {record.id}\ndata: {json.dumps(public(record))}\n\n"
                if len(records) < 100 and (not it or it.state in TERMINAL or it.paused):
                    yield "event: idle\ndata: {}\n\n"
                    return
            yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/versions/{vid}/export/{fmt}")
async def export(vid: str, fmt: str, db=Depends(get_db)):
    version = await need(db, m.ResumeVersion, vid)
    if fmt == "md":
        data = version.text.encode()
        media = "text/markdown; charset=utf-8"
    elif fmt == "docx":
        from docx import Document

        doc = Document()
        for line in version.text.splitlines():
            doc.add_paragraph(line)
        out = BytesIO()
        doc.save(out)
        data = out.getvalue()
        media = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    elif fmt == "pdf":
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        out = BytesIO()
        style = getSampleStyleSheet()["Normal"]
        blocks = []
        for line in version.text.splitlines():
            blocks.extend([Paragraph(escape(line) or " ", style), Spacer(1, 5)])
        SimpleDocTemplate(out).build(blocks)
        data = out.getvalue()
        media = "application/pdf"
    else:
        raise HTTPException(422, "Use md, docx or pdf")
    return StreamingResponse(
        BytesIO(data),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="resume-v{version.number}.{fmt}"'
        },
    )


@app.post("/metrics/{mid}/review")
async def review_metric(mid: str, body: s.MetricReviewRequest, db=Depends(get_db)):
    metric = await need(db, m.MetricEvidence, mid)
    project = await need(db, m.Project, metric.project_id)
    async with locks[project.resume_id]:
        await editable(db, project.resume_id)
        if metric.evidence_status == "VERIFIED":
            raise HTTPException(409, "Measurement already reviewed")
        # Human artifact review, distinct from an ordinary candidate assertion. Never an automatic verification.
        record = m.EvidenceRecord(
            resume_id=project.resume_id,
            text=body.supported_statement,
            source=f"Human-reviewed measurement artifact: {metric.source_reference}\nReview: {body.review_note}",
            status="VERIFIED",
            kind="measurement",
        )
        db.add(record)
        await db.flush()
        db.add(
            m.CandidateConfirmation(
                resume_id=project.resume_id,
                question=f"Review direct measurement artifact for {metric.metric_name}; not a candidate assertion",
                response=body.review_note,
                evidence_id=record.id,
            )
        )
        metric.evidence_status = "VERIFIED"
        await db.commit()
        return public(record)


@app.get("/provider")
async def provider_status():
    try:
        codex_status = await codex.status()
    except CodexError:
        codex_status = {
            "available": codex.available,
            "signed_in": False,
            "pending_login": None,
            "error": "Codex unavailable. Reconnect to try again.",
        }
    kind = getattr(workflow.provider, "kind", "openai")
    return {
        "provider": kind,
        "configured": codex_status["signed_in"]
        if kind == "codex"
        else bool(workflow.config.openai_api_key),
        "source": "codex"
        if kind == "codex"
        else (
            "session"
            if workflow.session_key_configured
            else ("environment" if workflow.config.openai_api_key else "none")
        ),
        "verified": False,
        "codex": codex_status,
    }


def allow_connection_change(request):
    origin = request.headers.get("origin")
    if origin and origin not in {settings().cors_origin, "http://127.0.0.1:3000"}:
        raise HTTPException(
            403, "Connection settings require the configured dashboard origin"
        )
    if any(not task.done() for task in workflow.tasks.values()):
        raise HTTPException(
            409, "Cancel active iterations before changing the provider connection"
        )


async def replace_provider(request, key):
    async with locks["provider_connection"]:
        allow_connection_change(request)
        old = workflow.provider
        config = workflow.config.model_copy(update={"openai_api_key": key})
        workflow.provider = OpenAIProvider(config)
        workflow.config = config
        if isinstance(old, OpenAIProvider):
            await old.client.close()


@app.post("/provider/connection")
async def connect_provider(body: s.ProviderConnectionRequest, request: Request):
    key = body.api_key.get_secret_value().strip()
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise HTTPException(422, "Enter a valid nonempty API key without whitespace")
    await replace_provider(request, key)
    workflow.session_key_configured = True
    return await provider_status()


@app.post("/provider/disconnect")
async def disconnect_provider(request: Request):
    await replace_provider(request, settings().openai_api_key)
    workflow.session_key_configured = False
    return await provider_status()


@app.post("/provider/select")
async def select_provider(body: s.ProviderSelectRequest, request: Request):
    async with locks["provider_connection"]:
        allow_connection_change(request)
        if body.provider == "codex":
            try:
                await codex.start()
                if not (await codex.status())["signed_in"]:
                    raise HTTPException(
                        409, "Sign in with ChatGPT before selecting Codex"
                    )
            except CodexError:
                raise HTTPException(
                    503, "Codex unavailable. Install the pinned CLI or check sign-in."
                )
            next_provider = CodexProvider(workflow.config, codex, workflow.sessions)
        else:
            next_provider = OpenAIProvider(workflow.config)
        old = workflow.provider
        workflow.provider = next_provider
        if isinstance(old, OpenAIProvider):
            await old.client.close()
    return await provider_status()


@app.post("/provider/codex/login")
async def codex_login(request: Request):
    async with locks["provider_connection"]:
        allow_connection_change(request)
        try:
            await codex.start()
            if not (await codex.status())["signed_in"]:
                await codex.begin_login()
        except CodexError:
            raise HTTPException(
                503,
                "Codex sign-in unavailable. Check CLI installation, network access and device-code login availability.",
            )
    return await provider_status()


@app.post("/provider/codex/logout")
async def codex_logout(request: Request):
    async with locks["provider_connection"]:
        allow_connection_change(request)
        try:
            await codex.logout()
        except CodexError:
            raise HTTPException(
                503,
                "Codex logout failed. Retry before assuming saved credentials were removed.",
            )
    return await provider_status()
