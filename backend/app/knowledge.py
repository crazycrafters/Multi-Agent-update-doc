"""Profile-scoped hybrid retrieval. Embeddings are optional; provenance is mandatory."""

import math
import re
from sqlalchemy import select, func, text, or_
from openai import AsyncOpenAI
from . import models as m
from .schemas import WorkspaceConfig


async def workspace_config(db):
    row = await db.get(m.WorkspaceSettings, "workspace")
    return WorkspaceConfig.model_validate(row.data if row else {}).model_dump()


def chunk_text(content, size=1000, overlap=150):
    result = []
    start = 0
    while start < len(content):
        end = min(start + size, len(content))
        if end < len(content):
            boundary = content.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        result.append(content[start:end])
        if end == len(content):
            break
        start = max(start + 1, end - overlap)
    return result


async def add_document(db, profile_id, data):
    data = dict(data)
    if data["kind"] == "reference":
        data["status"] = "PUBLIC_CONTEXT"
    if data["kind"] == "open_question":
        data["status"] = "UNVERIFIED"
    document = m.KnowledgeDocument(profile_id=profile_id, **data)
    db.add(document)
    await db.flush()
    for position, part in enumerate(chunk_text(document.content)):
        db.add(
            m.KnowledgeChunk(
                profile_id=profile_id,
                document_id=document.id,
                position=position,
                text=part,
            )
        )
    await db.flush()
    return document


class KnowledgeBudgetError(RuntimeError):
    pass


async def estimated_api_spend(db):
    agents = (
        await db.scalar(
            select(func.sum(m.AgentExecution.estimated_cost))
            .join(m.Iteration)
            .where(m.Iteration.provider == "openai")
        )
        or 0
    )
    embeddings = await db.scalar(select(func.sum(m.EmbeddingUsage.estimated_cost))) or 0
    return agents + embeddings


async def embed_texts(db, profile_id, texts, key):
    cfg = await workspace_config(db)
    if (
        cfg["api_budget_usd"] is not None
        and await estimated_api_spend(db) >= cfg["api_budget_usd"]
    ):
        raise KnowledgeBudgetError(
            "Configured API budget reached. Increase the budget in Settings before requesting embeddings."
        )
    if not key:
        raise ValueError(
            "An OpenAI API key is required for embeddings; Codex login does not provide embeddings"
        )
    async with AsyncOpenAI(api_key=key, timeout=60, max_retries=2) as client:
        result = await client.embeddings.create(
            model="text-embedding-3-small", dimensions=1536, input=texts
        )
    vectors = [x.embedding for x in sorted(result.data, key=lambda x: x.index)]
    if len(vectors) != len(texts) or any(
        len(v) != 1536 or not all(math.isfinite(x) for x in v) for v in vectors
    ):
        raise ValueError("Invalid embedding response")
    cfg = await workspace_config(db)
    tokens = result.usage.total_tokens
    rate = cfg["embedding_usd_per_million"]
    db.add(
        m.EmbeddingUsage(
            profile_id=profile_id,
            input_tokens=tokens,
            estimated_cost=None if rate is None else tokens * rate / 1e6,
        )
    )
    await db.flush()
    return vectors


async def retrieve(db, profile_id, query, limit=6, vector=None):
    base = (
        select(m.KnowledgeChunk, m.KnowledgeDocument)
        .join(
            m.KnowledgeDocument, m.KnowledgeDocument.id == m.KnowledgeChunk.document_id
        )
        .where(
            m.KnowledgeChunk.profile_id == profile_id,
            m.KnowledgeDocument.profile_id == profile_id,
            m.KnowledgeDocument.active.is_(True),
        )
    )
    ranked = {}
    records = {}

    def merge(items, weight=1):
        for rank, (chunk, doc) in enumerate(items):
            ranked[chunk.id] = ranked.get(chunk.id, 0) + weight / (60 + rank + 1)
            records[chunk.id] = (chunk, doc)

    if db.bind.dialect.name == "postgresql":
        search = func.websearch_to_tsquery(
            "english", " OR ".join(re.findall(r"\w+", query)[:48])
        )
        document = func.to_tsvector("english", m.KnowledgeChunk.text)
        metadata = func.to_tsvector(
            "english",
            func.concat(m.KnowledgeDocument.title, " ", m.KnowledgeDocument.project),
        )
        matches = (
            await db.execute(
                base.where(or_(document.op("@@")(search), metadata.op("@@")(search)))
                .order_by(
                    (
                        func.ts_rank_cd(document, search)
                        + func.ts_rank_cd(metadata, search)
                    ).desc()
                )
                .limit(30)
            )
        ).all()
        merge(matches)
        if vector is not None:
            merge(
                (
                    await db.execute(
                        base.where(
                            m.KnowledgeChunk.embedding.is_not(None),
                            m.KnowledgeChunk.embedding_model
                            == "text-embedding-3-small",
                        )
                        .order_by(m.KnowledgeChunk.embedding.cosine_distance(vector))
                        .limit(30)
                    )
                ).all()
            )
    else:
        terms = set(re.findall(r"\w+", query.lower()))
        matches = (await db.execute(base)).all()
        scored = []
        for chunk, doc in matches:
            score = sum(
                (chunk.text + " " + doc.title + " " + doc.project).lower().count(term)
                for term in terms
            )
            if score:
                scored.append((score, chunk, doc))
        merge(
            [
                (c, d)
                for _, c, d in sorted(scored, key=lambda x: x[0], reverse=True)[:30]
            ]
        )
        if vector is not None:
            candidates = [
                (c, d)
                for c, d in matches
                if c.embedding is not None
                and c.embedding_model == "text-embedding-3-small"
            ]

            def cosine(c):
                denom = math.sqrt(sum(x * x for x in c.embedding)) * math.sqrt(
                    sum(x * x for x in vector)
                )
                return (
                    sum(a * b for a, b in zip(c.embedding, vector)) / denom
                    if denom
                    else 0
                )

            merge(
                sorted(candidates, key=lambda pair: cosine(pair[0]), reverse=True)[:30]
            )
    result = []
    for identifier in sorted(ranked, key=ranked.get, reverse=True)[:limit]:
        chunk, doc = records[identifier]
        result.append(
            {
                "id": chunk.id,
                "document_id": doc.id,
                "title": doc.title,
                "project": doc.project,
                "text": chunk.text,
                "source": doc.source,
                "status": doc.status,
                "kind": doc.kind,
                "version": doc.version,
            }
        )
    return result


async def sync_personal_evidence(db, resume):
    documents = (
        await db.scalars(
            select(m.KnowledgeDocument).where(
                m.KnowledgeDocument.profile_id == resume.profile_id
            )
        )
    ).all()
    for doc in documents:
        existing = await db.scalar(
            select(m.EvidenceRecord).filter_by(
                resume_id=resume.id, knowledge_document_id=doc.id
            )
        )
        if not doc.active:
            if existing:
                existing.status = "UNVERIFIED"
            continue
        if doc.kind != "personal" or doc.status != "CANDIDATE_CONFIRMED":
            continue
        if not existing:
            db.add(
                m.EvidenceRecord(
                    resume_id=resume.id,
                    knowledge_document_id=doc.id,
                    text=doc.content,
                    source=f"Profile knowledge {doc.id}, version {doc.version}: {doc.source}",
                    status=doc.status,
                    kind="knowledge_personal",
                )
            )
    await db.flush()
