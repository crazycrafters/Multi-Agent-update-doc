import io
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from .database import get_db
from . import models as m, schemas as s
from .knowledge import (
    workspace_config,
    add_document,
    retrieve,
    embed_texts,
    sync_personal_evidence,
)
from .parsing import parse_resume, MAX_UPLOAD

router = APIRouter()


async def need(db, model, identifier):
    obj = await db.get(model, identifier)
    if obj is None:
        raise HTTPException(404, "Record not found")
    return obj


def public(obj):
    from .workflow import public

    return public(obj)


async def mutable_profile(db, pid):
    active = await db.scalar(
        select(m.Iteration.id)
        .join(m.Resume)
        .where(
            m.Resume.profile_id == pid,
            m.Iteration.state.not_in(
                {"AWAITING_APPROVAL", "FAILED", "COMPLETED", "CANCELLED"}
            ),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(
            409,
            "Wait for the current workflow or cancel it before editing profile knowledge",
        )


@router.get("/profiles")
async def profiles(db=Depends(get_db)):
    return [
        public(p)
        for p in (
            await db.scalars(select(m.Profile).order_by(m.Profile.created_at))
        ).all()
    ]


@router.post("/profiles", status_code=201)
async def profile_create(body: s.ProfileRequest, db=Depends(get_db)):
    row = m.Profile(**body.model_dump())
    db.add(row)
    await db.commit()
    return public(row)


@router.put("/profiles/{pid}")
async def profile_edit(pid: str, body: s.ProfileRequest, db=Depends(get_db)):
    await mutable_profile(db, pid)
    row = await need(db, m.Profile, pid)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    # Existing iteration targets remain immutable snapshots. New runs use this target.
    await db.commit()
    return public(row)


@router.get("/profiles/{pid}/knowledge")
async def documents(pid: str, db=Depends(get_db)):
    await need(db, m.Profile, pid)
    docs = (
        await db.scalars(
            select(m.KnowledgeDocument)
            .where(m.KnowledgeDocument.profile_id == pid)
            .order_by(m.KnowledgeDocument.created_at.desc())
            .limit(500)
        )
    ).all()
    result = []
    for doc in docs:
        chunks = await db.scalar(
            select(func.count())
            .select_from(m.KnowledgeChunk)
            .where(m.KnowledgeChunk.document_id == doc.id)
        )
        indexed = await db.scalar(
            select(func.count())
            .select_from(m.KnowledgeChunk)
            .where(
                m.KnowledgeChunk.document_id == doc.id,
                m.KnowledgeChunk.embedding.is_not(None),
            )
        )
        result.append({**public(doc), "chunks": chunks, "embedded_chunks": indexed})
    return result


@router.post("/profiles/{pid}/knowledge", status_code=201)
async def document_add(pid: str, body: s.KnowledgeRequest, db=Depends(get_db)):
    await need(db, m.Profile, pid)
    await mutable_profile(db, pid)
    row = await add_document(db, pid, body.model_dump())
    await db.commit()
    return public(row)


@router.post("/profiles/{pid}/knowledge/upload", status_code=201)
async def document_upload(
    pid: str,
    file: UploadFile = File(...),
    kind: str = Form("personal"),
    project: str = Form(""),
    db=Depends(get_db),
):
    import asyncio

    await need(db, m.Profile, pid)
    await mutable_profile(db, pid)
    try:
        content = await asyncio.to_thread(
            parse_resume, file.filename or "", await file.read(MAX_UPLOAD + 1)
        )
    except Exception:
        raise HTTPException(
            422, "Use a readable text, Markdown, DOCX or PDF file up to 2 MB"
        )
    try:
        body = s.KnowledgeRequest(
            title=(file.filename or "Document")[:200],
            kind=kind,
            project=project,
            source=file.filename or "Uploaded document",
            content=content,
        )
    except ValueError:
        raise HTTPException(422, "Invalid document metadata")
    row = await add_document(db, pid, body.model_dump())
    await db.commit()
    return public(row)


@router.put("/profiles/{pid}/knowledge/{did}")
async def document_edit(
    pid: str, did: str, body: s.KnowledgeRequest, db=Depends(get_db)
):
    await mutable_profile(db, pid)
    old = await need(db, m.KnowledgeDocument, did)
    if old.profile_id != pid:
        raise HTTPException(404, "Record not found")
    if not old.active:
        raise HTTPException(409, "Archived versions cannot be revised")
    old.active = False
    row = await add_document(db, pid, body.model_dump())
    row.version = old.version + 1
    await db.commit()
    return public(row)


@router.post("/profiles/{pid}/knowledge/{did}/archive")
async def document_archive(pid: str, did: str, db=Depends(get_db)):
    await mutable_profile(db, pid)
    doc = await need(db, m.KnowledgeDocument, did)
    if doc.profile_id != pid:
        raise HTTPException(404, "Record not found")
    doc.active = False
    await db.commit()
    return public(doc)


@router.post("/profiles/{pid}/knowledge/{did}/embed")
async def document_embed(
    pid: str, did: str, body: s.EmbeddingRequest, db=Depends(get_db)
):
    from .main import workflow

    if not body.consent:
        raise HTTPException(
            422,
            "Explicit consent to send document text to OpenAI embeddings is required",
        )
    await mutable_profile(db, pid)
    doc = await need(db, m.KnowledgeDocument, did)
    if doc.profile_id != pid:
        raise HTTPException(404, "Record not found")
    if not doc.active:
        raise HTTPException(409, "Cannot embed archived documents")
    chunks = list(
        (
            await db.scalars(
                select(m.KnowledgeChunk)
                .where(
                    m.KnowledgeChunk.document_id == did,
                    m.KnowledgeChunk.profile_id == pid,
                    or_(
                        m.KnowledgeChunk.embedding.is_(None),
                        m.KnowledgeChunk.embedding_model.is_(None),
                        m.KnowledgeChunk.embedding_model != "text-embedding-3-small",
                    ),
                )
                .order_by(m.KnowledgeChunk.position)
            )
        ).all()
    )
    key = workflow.config.openai_api_key
    if not key:
        raise HTTPException(
            503, "Connect an OpenAI key for embeddings, even when using Codex"
        )
    for offset in range(0, len(chunks), 32):
        batch = chunks[offset : offset + 32]
        vectors = await embed_texts(db, pid, [c.text for c in batch], key)
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector
            chunk.embedding_model = "text-embedding-3-small"
        await db.commit()
    await db.commit()
    return {"indexed": len(chunks)}


@router.post("/profiles/{pid}/knowledge/search")
async def knowledge_search(pid: str, body: s.SearchRequest, db=Depends(get_db)):
    from .main import workflow

    await need(db, m.Profile, pid)
    vector = None
    if body.semantic:
        if not body.embedding_consent:
            raise HTTPException(422, "Embedding consent required for semantic search")
        if not workflow.config.openai_api_key:
            raise HTTPException(503, "OpenAI embedding key not configured")
        vector = (
            await embed_texts(db, pid, [body.query], workflow.config.openai_api_key)
        )[0]
    results = await retrieve(db, pid, body.query, body.limit, vector)
    await db.commit()
    return {
        "results": results,
        "method": "hybrid" if vector is not None else "full_text",
    }


@router.get("/profiles/{pid}/knowledge/export")
async def export_knowledge(pid: str, format: str = "json", db=Depends(get_db)):
    profile = await need(db, m.Profile, pid)
    docs = (
        await db.scalars(
            select(m.KnowledgeDocument).where(
                m.KnowledgeDocument.profile_id == pid,
                m.KnowledgeDocument.active.is_(True),
            )
        )
    ).all()
    evidence = (
        await db.scalars(
            select(m.EvidenceRecord)
            .join(m.Resume)
            .where(
                m.Resume.profile_id == pid,
                m.EvidenceRecord.knowledge_document_id.is_(None),
            )
        )
    ).all()
    confirmations = (
        await db.scalars(
            select(m.CandidateConfirmation)
            .join(m.Resume)
            .where(m.Resume.profile_id == pid)
        )
    ).all()
    if format == "md":
        content = f"# {profile.name}\nTarget: {profile.target_role}\n\n"
        for doc in docs:
            content += f"## {doc.title}\nID: {doc.id} | {doc.kind} | {doc.status} | version {doc.version}\nSource: {doc.source}\n\n{doc.content}\n\n"
        content += "## Personal evidence records\n\n"
        for item in evidence:
            content += f"### {item.id} — {item.status}\nSource: {item.source}\n\n{item.text}\n\n"
        content += "## Unresolved questions — not factual evidence\n\n"
        for item in confirmations:
            if not item.response:
                content += f"- {item.question}\n"
        return Response(
            content,
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="knowledge.md"'},
        )
    if format != "json":
        raise HTTPException(422, "Use json or md")
    chunks = (
        await db.scalars(
            select(m.KnowledgeChunk)
            .join(m.KnowledgeDocument)
            .where(
                m.KnowledgeChunk.profile_id == pid,
                m.KnowledgeDocument.profile_id == pid,
                m.KnowledgeDocument.active.is_(True),
            )
        )
    ).all()
    data = {
        "schema_version": 1,
        "evidence": [public(e) for e in evidence],
        "confirmations": [public(e) for e in confirmations],
        "profile": public(profile),
        "documents": [public(d) for d in docs],
        "chunks": [
            {k: v for k, v in public(c).items() if k != "embedding"} for c in chunks
        ],
    }
    return Response(
        json.dumps(data),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="knowledge.json"'},
    )


@router.get("/settings")
async def settings_read(db=Depends(get_db)):
    return await workspace_config(db)


@router.put("/settings")
async def settings_write(body: s.WorkspaceConfig, db=Depends(get_db)):
    row = await db.get(m.WorkspaceSettings, "workspace")
    if row:
        row.data = body.model_dump()
    else:
        db.add(m.WorkspaceSettings(id="workspace", data=body.model_dump()))
    await db.commit()
    return body.model_dump()


@router.get("/usage")
async def usage(db=Depends(get_db)):
    from .main import workflow, codex

    cfg = await workspace_config(db)
    executions = (
        await db.execute(
            select(m.AgentExecution, m.Iteration.provider).join(m.Iteration)
        )
    ).all()
    api = [e for e, p in executions if p == "openai"]
    codex_calls = [e for e, p in executions if p == "codex"]
    embedding = (await db.scalars(select(m.EmbeddingUsage))).all()
    known = sum(e.estimated_cost or 0 for e in api) + sum(
        e.estimated_cost or 0 for e in embedding
    )
    unknown = sum(
        e.estimated_cost is None
        for e in api
        if e.status in {"completed", "failed", "interrupted"}
    ) + sum(e.estimated_cost is None for e in embedding)
    budget = cfg["api_budget_usd"]
    remaining = None if budget is None or unknown else max(0, budget - known)
    limits = None
    if getattr(workflow.provider, "kind", "openai") == "codex" and getattr(
        codex, "process", None
    ):
        try:
            raw = await codex.rpc("account/rateLimits/read")
            limits = {}
            for field in ["primary", "secondary"]:
                window = raw.get("rateLimits", {}).get(field)
                if window:
                    limits[field] = {
                        k: window.get(k)
                        for k in ["usedPercent", "windowDurationMins", "resetsAt"]
                    }
        except Exception:
            limits = None
    return {
        "provider": getattr(workflow.provider, "kind", "openai"),
        "api": {
            "budget_usd": budget,
            "estimated_spent_usd": known,
            "remaining_budget_usd": remaining,
            "unpriced_calls": unknown,
            "account_balance_available": False,
        },
        "codex": {
            "tokens": sum(e.input_tokens + e.output_tokens for e in codex_calls),
            "limits": limits,
        },
        "tokens": sum(e.input_tokens + e.output_tokens for e, p in executions)
        + sum(e.input_tokens for e in embedding),
    }


@router.post("/iterations/{iid}/strategies/select")
async def select_strategy(iid: str, body: s.StrategySelection, db=Depends(get_db)):
    from .main import workflow, locks

    it = await need(db, m.Iteration, iid)
    async with locks[it.resume_id]:
        await db.refresh(it)
        if it.state != "AWAITING_APPROVAL" or it.checkpoint.get("selected_strategy"):
            raise HTTPException(409, "Strategy is not selectable")
        selected = next(
            (
                x
                for x in it.checkpoint.get("strategies", [])
                if x["id"] == body.strategy_id
            ),
            None,
        )
        if not selected:
            raise HTTPException(422, "Choose a proposed strategy")
        # Persist selection first. Explicit Resume runs the selected, audited revision after a crash.
        it.checkpoint = {**it.checkpoint, "selected_strategy": selected}
        it.state = "EVIDENCE_VALIDATION"
        await db.commit()
        workflow.launch(iid)
        return public(it)
