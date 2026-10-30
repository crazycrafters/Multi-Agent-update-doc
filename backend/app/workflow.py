import asyncio
import json
import logging
from typing import TypedDict
from sqlalchemy import select, func
from langgraph.graph import StateGraph, END
from . import models as m, schemas as s
from .database import Session
from .config import settings
from .agents import OpenAIProvider
from .evidence import check_edit
from .knowledge import add_document, estimated_api_spend
from .knowledge import retrieve, sync_personal_evidence, embed_texts, workspace_config

log = logging.getLogger("workflow")
TERMINAL = {"AWAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"}
PHASES = [
    "RESUME_ANALYSIS",
    "RESUME_DRAFTING",
    "INTERVIEW_PREPARATION",
    "INTERVIEWING",
    "INTERVIEW_EVALUATION",
    "RESEARCHING",
    "EVIDENCE_VALIDATION",
    "RESUME_REVISION",
]


async def rows(db, model, **kw):
    return list(
        (
            await db.scalars(
                select(model).filter_by(**kw).order_by(model.created_at, model.id)
            )
        ).all()
    )


def public(obj):
    return {
        c.name: (
            getattr(obj, c.name).isoformat()
            if hasattr(getattr(obj, c.name), "isoformat")
            else getattr(obj, c.name)
        )
        for c in obj.__table__.columns
    }


async def event(db, iteration_id, agent, kind, data):
    db.add(m.AgentEvent(iteration_id=iteration_id, agent=agent, kind=kind, data=data))


async def create_version(db, resume, text, reason):
    n = (
        await db.scalar(
            select(func.max(m.ResumeVersion.number)).where(
                m.ResumeVersion.resume_id == resume.id
            )
        )
        or 0
    )
    version = m.ResumeVersion(
        resume_id=resume.id, number=n + 1, text=text, reason=reason
    )
    db.add(version)
    await db.flush()
    for pos, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        claim = m.Claim(
            version_id=version.id,
            text=line,
            status="UNVERIFIED",
            warning="Candidate evidence required",
        )
        db.add(claim)
        await db.flush()
        db.add(
            m.ResumeBullet(
                version_id=version.id, claim_id=claim.id, text=line, position=pos
            )
        )
    resume.current_version_id = version.id
    return version


class WorkState(TypedDict):
    iteration_id: str
    phase: str


class Workflow:
    def __init__(self, session_factory=Session, provider=None, config=None):
        self.sessions = session_factory
        self.config = config or settings()
        self.provider = provider or OpenAIProvider(self.config)
        self.tasks = {}
        self.wakeups = set()
        self.session_key_configured = False
        graph = StateGraph(WorkState)
        for phase in PHASES:
            graph.add_node(phase, self.node)
            graph.add_edge(phase, END)
        graph.set_conditional_entry_point(
            lambda state: state["phase"], {x: x for x in PHASES}
        )
        self.graph = graph.compile()

    def launch(self, iteration_id):
        if iteration_id not in self.tasks or self.tasks[iteration_id].done():
            self.tasks[iteration_id] = asyncio.create_task(self.run(iteration_id))
        elif iteration_id not in self.wakeups:
            self.wakeups.add(iteration_id)

            def wake(task):
                self.wakeups.discard(iteration_id)
                if not task.cancelled():
                    self.launch(iteration_id)

            self.tasks[iteration_id].add_done_callback(wake)

    async def shutdown(self):
        for t in self.tasks.values():
            t.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def recover(self):
        async with self.sessions() as db:
            active = list(
                (
                    await db.scalars(
                        select(m.Iteration).where(m.Iteration.state.not_in(TERMINAL))
                    )
                ).all()
            )
            for it in active:
                # Explicitly pause restored workflows; external calls may have been billed before a crash.
                it.paused = True
                await event(
                    db,
                    it.id,
                    "system",
                    "recovery",
                    {
                        "message": "Recovered checkpoint. Resume explicitly; an interrupted provider call may be repeated."
                    },
                )
            for ex in (
                await db.scalars(
                    select(m.AgentExecution).where(m.AgentExecution.status == "running")
                )
            ).all():
                ex.status = "interrupted"
            await db.commit()

    async def context(self, db, it):
        resume = await db.get(m.Resume, it.resume_id)
        version = await db.get(m.ResumeVersion, it.version_id)
        session = await db.scalar(
            select(m.InterviewSession).where(m.InterviewSession.iteration_id == it.id)
        )
        transcript = []
        if session:
            for q in await rows(db, m.InterviewQuestion, session_id=session.id):
                a = await db.scalar(
                    select(m.InterviewAnswer).where(
                        m.InterviewAnswer.question_id == q.id
                    )
                )
                e = await db.scalar(
                    select(m.InterviewEvaluation).where(
                        m.InterviewEvaluation.question_id == q.id
                    )
                )
                transcript.append(
                    {
                        "question": public(q),
                        "answer": public(a) if a else None,
                        "evaluation": public(e) if e else None,
                    }
                )
        past = list(
            (
                await db.scalars(
                    select(m.InterviewQuestion.text)
                    .join(m.InterviewSession)
                    .join(m.Iteration)
                    .where(
                        m.Iteration.resume_id == it.resume_id, m.Iteration.id != it.id
                    )
                    .order_by(m.InterviewQuestion.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        profile = await db.get(m.Profile, resume.profile_id)
        return {
            "profile_id": resume.profile_id,
            "target_role": it.checkpoint.get("target_role", profile.target_role),
            "job_description": it.checkpoint.get(
                "job_description", profile.job_description
            ),
            "resume": version.text,
            "claims": [
                public(x) for x in await rows(db, m.Claim, version_id=it.version_id)
            ],
            "evidence": [
                public(x)
                for x in await rows(db, m.EvidenceRecord, resume_id=it.resume_id)
                if x.knowledge_document_id is None
            ],
            "metrics": [
                public(x)
                for x in (
                    await db.scalars(
                        select(m.MetricEvidence)
                        .join(m.Project)
                        .where(m.Project.resume_id == it.resume_id)
                    )
                ).all()
            ],
            "transcript": transcript,
            "previous_questions": past,
            "checkpoint": it.checkpoint,
        }

    async def call(self, it_id, agent, task, context, schema=None, topics=None):
        async with self.sessions() as db:
            cached = await db.scalar(
                select(m.AgentExecution).where(
                    m.AgentExecution.iteration_id == it_id,
                    m.AgentExecution.task == task,
                    m.AgentExecution.status == "completed",
                )
            )
            if cached:
                return cached.output
            current = await db.get(m.Iteration, it_id)
            if current.cancel_requested:
                raise RuntimeError("Workflow cancelled")
            used = (
                await db.scalar(
                    select(
                        func.sum(
                            m.AgentExecution.input_tokens
                            + m.AgentExecution.output_tokens
                        )
                    ).where(m.AgentExecution.iteration_id == it_id)
                )
                or 0
            )
            if used >= self.config.max_iteration_tokens:
                raise RuntimeError("Iteration token budget reached")
            cfg = current.checkpoint.get("settings", {})
            if getattr(self.provider, "kind", "openai") == "openai":
                budget = (await workspace_config(db))["api_budget_usd"]
                spent = await estimated_api_spend(db)
                if budget is not None and spent >= budget:
                    raise RuntimeError("Configured API spending budget reached")
            strategy = cfg.get("strategies", {}).get(agent, "")
            if topics is None:
                safe_checkpoint = {
                    k: v
                    for k, v in context.get("checkpoint", {}).items()
                    if k
                    not in {
                        "settings",
                        "embedding_consent",
                        "target_role",
                        "job_description",
                    }
                }
                context = {
                    **context,
                    "checkpoint": safe_checkpoint,
                    "working_strategy": strategy,
                    "strategy_constraints": "Preferences never override evidence, privacy or approval safeguards.",
                }
            if topics is None and "profile_id" in context:
                resume = await db.get(m.Resume, current.resume_id)
                question = (
                    context.get("current_question", {}).get("text")
                    or context.get("question", {}).get("text")
                    or (
                        context.get("target_role", "")
                        + " "
                        + context.get("resume", "")[:1500]
                    )
                )
                claim_ids = set(
                    context.get("current_question", {}).get("claim_ids", [])
                )
                related = " ".join(
                    c["text"] for c in context.get("claims", []) if c["id"] in claim_ids
                )
                if related:
                    question = related + " " + question
                vector = None
                if cfg.get("workflow", {}).get(
                    "semantic_retrieval"
                ) and current.checkpoint.get("embedding_consent"):
                    vector = (
                        await embed_texts(
                            db,
                            resume.profile_id,
                            [question[:2000]],
                            self.config.openai_api_key,
                        )
                    )[0]
                knowledge = await retrieve(
                    db, resume.profile_id, question[:2000], vector=vector
                )
                doc_ids = {x["document_id"] for x in knowledge}
                supported = (
                    (
                        await db.scalars(
                            select(m.EvidenceRecord).where(
                                m.EvidenceRecord.resume_id == resume.id,
                                m.EvidenceRecord.knowledge_document_id.in_(doc_ids),
                            )
                        )
                    ).all()
                    if doc_ids
                    else []
                )
                context = {
                    **context,
                    "knowledge": knowledge,
                    "evidence": context.get("evidence", [])
                    + [
                        {
                            **public(x),
                            "text": "\n...\n".join(
                                p["text"]
                                for p in knowledge
                                if p["document_id"] == x.knowledge_document_id
                            ),
                        }
                        for x in supported
                    ],
                }
                await event(
                    db,
                    it_id,
                    agent,
                    "knowledge_retrieved",
                    {
                        "query": question,
                        "passages": knowledge,
                        "profile_id": resume.profile_id,
                    },
                )
            ex = m.AgentExecution(
                iteration_id=it_id,
                agent=agent,
                task=task,
                model=self.provider.model(agent),
            )
            db.add(ex)
            await db.flush()
            exid = ex.id
            await event(db, it_id, agent, "task_started", {"task": task})
            await db.commit()

        async def snapshot(text):
            async with self.sessions() as db:
                await event(
                    db,
                    it_id,
                    agent,
                    "answer_snapshot",
                    {"task": task, "execution_id": exid, "text": text},
                )
                await db.commit()

        try:
            if topics is not None:
                result = await self.provider.research(topics, scope=it_id)
            else:
                result = await self.provider.generate(
                    agent, task, context, schema, on_snapshot=snapshot, scope=it_id
                )
            if schema:
                result.data = schema.model_validate(result.data).model_dump(mode="json")
                if schema is s.Answer:
                    allowed = {x["id"] for x in context.get("knowledge", [])}
                    if set(result.data.get("knowledge_ids", [])) - allowed:
                        raise RuntimeError(
                            "Answer cited knowledge outside the retrieved profile context"
                        )
            async with self.sessions() as db:
                ex = await db.get(m.AgentExecution, exid)
                ex.status = "completed"
                ex.output = result.data
                ex.input_tokens = result.input_tokens
                ex.output_tokens = result.output_tokens
                c = self.config.model_copy(
                    update={
                        "input_usd_per_million": cfg.get("input_usd_per_million")
                        if cfg.get("input_usd_per_million") is not None
                        else self.config.input_usd_per_million,
                        "output_usd_per_million": cfg.get("output_usd_per_million")
                        if cfg.get("output_usd_per_million") is not None
                        else self.config.output_usd_per_million,
                        "web_search_usd_per_call": cfg.get("search_usd_per_call")
                        if cfg.get("search_usd_per_call") is not None
                        else self.config.web_search_usd_per_call,
                    }
                )
                if (
                    getattr(self.provider, "kind", "openai") == "openai"
                    and c.input_usd_per_million is not None
                    and c.output_usd_per_million is not None
                    and (
                        not result.search_calls or c.web_search_usd_per_call is not None
                    )
                ):
                    ex.estimated_cost = (
                        result.input_tokens * c.input_usd_per_million
                        + result.output_tokens * c.output_usd_per_million
                    ) / 1e6 + result.search_calls * (c.web_search_usd_per_call or 0)
                await event(
                    db,
                    it_id,
                    agent,
                    "task_completed",
                    {
                        "task": task,
                        "output": result.data,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "estimated_cost": ex.estimated_cost,
                    },
                )
                await db.commit()
            return result.data
        except BaseException:
            async with self.sessions() as db:
                ex = await db.get(m.AgentExecution, exid)
                ex.status = (
                    "interrupted" if asyncio.current_task().cancelling() else "failed"
                )
                await db.commit()
            raise

    async def run(self, it_id):
        try:
            while True:
                async with self.sessions() as db:
                    it = await db.get(m.Iteration, it_id)
                    if not it or it.state in TERMINAL:
                        return
                    if it.provider != getattr(self.provider, "kind", "openai"):
                        raise RuntimeError(
                            "Select the iteration's original provider before resuming"
                        )
                    if it.cancel_requested:
                        it.state = "CANCELLED"
                        await event(
                            db, it.id, "system", "state", {"state": "CANCELLED"}
                        )
                        await db.commit()
                        return
                    paused = it.paused
                    phase = it.state if it.state in PHASES else PHASES[0]
                if paused:
                    await asyncio.sleep(0.25)
                    continue
                await self.graph.ainvoke({"iteration_id": it_id, "phase": phase})
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Store only exception class. Provider error bodies may contain input or secrets.
            log.error(
                "workflow_failed",
                extra={"iteration_id": it_id, "error_type": type(exc).__name__},
            )
            async with self.sessions() as db:
                it = await db.get(m.Iteration, it_id)
                it.checkpoint = {**it.checkpoint, "failed_phase": it.state}
                it.state = "CANCELLED" if it.cancel_requested else "FAILED"
                it.error = f"{type(exc).__name__}: operation failed. Check provider configuration, connectivity and budget; retry resumes the checkpoint."
                await event(db, it_id, "system", "error", {"message": it.error})
                await db.commit()

    async def node(self, state):
        it_id = state["iteration_id"]
        phase = state["phase"]
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            it.state = phase
            resume = await db.get(m.Resume, it.resume_id)
            await sync_personal_evidence(db, resume)
            ctx = await self.context(db, it)
            await event(db, it.id, "system", "state", {"state": phase})
            await db.commit()
        handler = getattr(self, phase.lower())
        await handler(it_id, ctx)
        return state

    async def advance(self, db, it, next_phase, updates=None):
        # Refresh control flags after long external calls. They are never overwritten by stale state.
        await db.refresh(it, ["paused", "cancel_requested"])
        it.state = "CANCELLED" if it.cancel_requested else next_phase
        if updates:
            it.checkpoint = {**it.checkpoint, **updates}
        await db.commit()

    async def resume_analysis(self, it_id, ctx):
        output = await self.call(
            it_id,
            "resume",
            "Analyze target fit, evidence gaps and conflicts",
            ctx,
            s.Analysis,
        )
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            for q in output["confirmation_questions"]:
                db.add(
                    m.CandidateConfirmation(
                        resume_id=it.resume_id, iteration_id=it.id, question=q
                    )
                )
            await self.advance(db, it, "RESUME_DRAFTING", {"analysis": output})

    async def propose(self, it_id, ctx, label):
        proposal = await self.call(it_id, "resume", label, ctx, s.Proposal)
        audit = await self.call(
            it_id,
            "resume",
            label + " — independent evidence audit",
            {
                **ctx,
                "proposal": proposal,
                "audit_mode": "independent; evaluate every edit from evidence, not writer confidence",
            },
            s.Audit,
        )
        return {"proposal": proposal, "audit": audit}

    async def resume_drafting(self, it_id, ctx):
        if (
            not ctx["checkpoint"]
            .get("settings", {})
            .get("workflow", {})
            .get("initial_draft", True)
        ):
            async with self.sessions() as db:
                it = await db.get(m.Iteration, it_id)
                await self.advance(db, it, "INTERVIEW_PREPARATION")
            return
        result = await self.propose(
            it_id, ctx, "Draft evidence-grounded target-role improvements"
        )
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            await self.apply_edits(db, it, result, "initial draft")
            await self.advance(db, it, "INTERVIEW_PREPARATION", {"draft": result})

    async def interview_preparation(self, it_id, ctx):
        await self.call(
            it_id,
            "interviewee",
            "Study this resume and evidence; report readiness and limitations",
            ctx,
            s.Answer,
        )
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            if not await db.scalar(
                select(m.InterviewSession).where(
                    m.InterviewSession.iteration_id == it.id
                )
            ):
                db.add(m.InterviewSession(iteration_id=it.id, version_id=it.version_id))
            await self.advance(db, it, "INTERVIEWING")

    async def interviewing(self, it_id, ctx):
        async with self.sessions() as db:
            session = await db.scalar(
                select(m.InterviewSession).where(
                    m.InterviewSession.iteration_id == it_id
                )
            )
            questions = await rows(db, m.InterviewQuestion, session_id=session.id)
            for q in questions:
                if not await db.scalar(
                    select(m.InterviewEvaluation).where(
                        m.InterviewEvaluation.question_id == q.id
                    )
                ):
                    await self.answer_evaluate(it_id, q, ctx)
                    return
            # Add one adaptive follow-up when requested, persisted separately from primary questions.
            if questions:
                last = questions[-1]
                evaluation = await db.scalar(
                    select(m.InterviewEvaluation).where(
                        m.InterviewEvaluation.question_id == last.id
                    )
                )
                if (
                    not last.followup
                    and evaluation.followup
                    and ctx["checkpoint"]
                    .get("settings", {})
                    .get("workflow", {})
                    .get("followups", True)
                ):
                    q = m.InterviewQuestion(
                        session_id=session.id,
                        number=last.number,
                        followup=True,
                        text=evaluation.followup,
                        claim_ids=last.claim_ids,
                        difficulty=last.difficulty,
                    )
                    db.add(q)
                    await db.commit()
                    return
            count = sum(not q.followup for q in questions)
            question_count = (
                ctx["checkpoint"]
                .get("settings", {})
                .get("workflow", {})
                .get("question_count", 10)
            )
            if count >= question_count:
                it = await db.get(m.Iteration, it_id)
                await self.advance(db, it, "INTERVIEW_EVALUATION")
                return
        data = await self.call(
            it_id,
            "interviewer",
            f"Generate primary question {count + 1} of {question_count}, adaptive to previous answers",
            ctx,
            s.Question,
        )
        async with self.sessions() as db:
            db.add(
                m.InterviewQuestion(
                    session_id=session.id, number=count + 1, followup=False, **data
                )
            )
            await db.commit()

    async def answer_evaluate(self, it_id, q, ctx):
        label = f"Question {q.number}" + (" follow-up" if q.followup else "")
        answer = await self.call(
            it_id,
            "interviewee",
            label + " answer",
            {**ctx, "current_question": public(q)},
            s.Answer,
        )
        async with self.sessions() as db:
            if not await db.scalar(
                select(m.InterviewAnswer).where(m.InterviewAnswer.question_id == q.id)
            ):
                db.add(
                    m.InterviewAnswer(
                        question_id=q.id,
                        knowledge_ids=answer.get("knowledge_ids", []),
                        text=answer["text"],
                        limitations=answer["limitations"],
                        actor="simulated",
                    )
                )
                await db.commit()
        evaluation = await self.call(
            it_id,
            "interviewer",
            label + " evaluation",
            {**ctx, "question": public(q), "answer": answer},
            s.Evaluation,
        )
        async with self.sessions() as db:
            db.add(
                m.InterviewEvaluation(
                    question_id=q.id,
                    scores=evaluation["scores"],
                    weaknesses=evaluation["weaknesses"],
                    followup=None if q.followup else evaluation["followup"],
                )
            )
            await db.commit()

    async def interview_evaluation(self, it_id, ctx):
        report = await self.call(
            it_id,
            "interviewee",
            "Summarize the completed interview; simulated answers are not evidence",
            ctx,
            s.Feedback,
        )
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            session = await db.scalar(
                select(m.InterviewSession).where(
                    m.InterviewSession.iteration_id == it_id
                )
            )
            db.add(
                m.WeaknessReport(
                    iteration_id=it_id, session_id=session.id, report=report
                )
            )
            for q in report["confirmation_questions"]:
                db.add(
                    m.CandidateConfirmation(
                        resume_id=it.resume_id, iteration_id=it_id, question=q
                    )
                )
            await self.advance(db, it, "RESEARCHING", {"feedback": report})

    async def researching(self, it_id, ctx):
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            consent = it.research_consent and it.checkpoint.get("settings", {}).get(
                "workflow", {}
            ).get("research", True)
        topics = ctx["checkpoint"].get("feedback", {}).get("research_topics", [])[:4]
        notes = {"findings": [], "study_recommendations": []}
        if consent and topics:
            raw = await self.call(
                it_id,
                "resume",
                "Search public sources for generic research topics",
                {},
                topics=topics,
            )
            if raw["sources"]:
                notes = await self.call(
                    it_id,
                    "resume",
                    "Extract attributed research findings; public context only",
                    {"research": raw},
                    s.ResearchNotes,
                )
            else:
                notes = {
                    "findings": [],
                    "study_recommendations": [
                        "No attributable research sources were found. Preserve unsupported claims for candidate review."
                    ],
                }
            async with self.sessions() as db:
                existing = {
                    x.url for x in await rows(db, m.ResearchSource, iteration_id=it_id)
                }
                for source in raw["sources"]:
                    if source["url"] in existing:
                        continue
                    src = m.ResearchSource(
                        iteration_id=it_id, **source, publication_date=None
                    )
                    db.add(src)
                    await db.flush()
                    for finding in notes["findings"]:
                        if finding["source_url"] == source["url"]:
                            db.add(m.ResearchFinding(source_id=src.id, details=finding))
                resume = await db.get(m.Resume, it.resume_id)
                for source in raw["sources"]:
                    relevant = [
                        f for f in notes["findings"] if f["source_url"] == source["url"]
                    ]
                    exists = await db.scalar(
                        select(m.KnowledgeDocument.id)
                        .where(
                            m.KnowledgeDocument.profile_id == resume.profile_id,
                            m.KnowledgeDocument.source == source["url"],
                            m.KnowledgeDocument.active.is_(True),
                        )
                        .limit(1)
                    )
                    if relevant and not exists:
                        content = (
                            "AI-generated technical reference summary; not personal experience. Verify the cited source.\n\n"
                            + "\n\n".join(
                                json.dumps(f, ensure_ascii=False) for f in relevant
                            )
                        )
                        await add_document(
                            db,
                            resume.profile_id,
                            {
                                "title": ("Research: " + source["title"])[:200],
                                "project": "",
                                "kind": "reference",
                                "status": "PUBLIC_CONTEXT",
                                "source": source["url"],
                                "content": content,
                            },
                        )
                await db.commit()
        else:
            async with self.sessions() as db:
                await event(
                    db,
                    it_id,
                    "resume",
                    "research_skipped",
                    {
                        "reason": "No external-search consent"
                        if not consent
                        else "No research topics"
                    },
                )
                await db.commit()
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            await self.advance(db, it, "EVIDENCE_VALIDATION", {"research": notes})

    async def evidence_validation(self, it_id, ctx):
        selected = ctx["checkpoint"].get("selected_strategy")
        label = (
            "Revise after interview and research; no unsupported historical additions"
        )
        if selected:
            label += (
                " — selected strategy " + selected["id"] + ": " + selected["summary"]
            )
        result = await self.propose(it_id, ctx, label)
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            await self.advance(db, it, "RESUME_REVISION", {"revision": result})

    async def resume_revision(self, it_id, ctx):
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            intermediate = it.run_step < it.planned_iterations
            selected = it.checkpoint.get("selected_strategy")
        options = None
        if not intermediate and not selected:
            options = await self.call(
                it_id,
                "resume",
                "Propose 2 to 4 distinct, evidence-grounded resume update strategies. Use 2–5 words per title and one sentence under 20 words per summary. Do not apply edits yet.",
                ctx,
                s.StrategyOptions,
            )
            if len({x["id"] for x in options["options"]}) != len(options["options"]):
                raise RuntimeError("Strategy identifiers must be unique")
        async with self.sessions() as db:
            it = await db.get(m.Iteration, it_id)
            await db.refresh(it, ["cancel_requested", "paused"])
            if it.cancel_requested:
                await self.advance(db, it, "CANCELLED")
                return
            if intermediate or selected:
                await self.apply_edits(
                    db,
                    it,
                    it.checkpoint["revision"],
                    "Selected strategy"
                    if selected
                    else "Batch evidence-grounded revision",
                )
            it.output_version_id = it.version_id
            if intermediate:
                successor = m.Iteration(
                    resume_id=it.resume_id,
                    version_id=it.version_id,
                    number=it.number + 1,
                    run_id=it.run_id,
                    run_step=it.run_step + 1,
                    planned_iterations=it.planned_iterations,
                    provider=it.provider,
                    provider_consent=it.provider_consent,
                    research_consent=it.research_consent,
                    paused=it.paused,
                    state="RESUME_ANALYSIS",
                    checkpoint={
                        k: v
                        for k, v in it.checkpoint.items()
                        if k
                        in [
                            "settings",
                            "embedding_consent",
                            "target_role",
                            "job_description",
                        ]
                    },
                )
                db.add(successor)
                await db.flush()
                await event(
                    db,
                    it.id,
                    "system",
                    "batch_continues",
                    {
                        "next_iteration_id": successor.id,
                        "step": successor.run_step,
                        "total": it.planned_iterations,
                    },
                )
                await self.advance(db, it, "COMPLETED")
                self.launch(successor.id)
            else:
                if options:
                    it.checkpoint = {**it.checkpoint, "strategies": options["options"]}
                await event(
                    db,
                    it.id,
                    "resume",
                    "strategy_choices" if options else "approval_required",
                    {
                        "options": options["options"] if options else [],
                        "message": "Choose an update strategy. No new batch starts automatically."
                        if options
                        else "Selected strategy applied only where evidence supports it.",
                    },
                )
                await self.advance(db, it, "AWAITING_APPROVAL")

    async def apply_edits(self, db, it, result, reason):
        await db.refresh(it, ["cancel_requested"])
        if it.cancel_requested:
            return
        resume = await db.get(m.Resume, it.resume_id)
        old = await db.get(m.ResumeVersion, it.version_id)
        claims = {x.id: x for x in await rows(db, m.Claim, version_id=old.id)}
        evidence = {
            x.id: x for x in await rows(db, m.EvidenceRecord, resume_id=resume.id)
        }
        audits = {x["claim_id"]: x for x in result["audit"]["items"]}
        conflict = await db.scalar(
            select(m.KnowledgeDocument.id)
            .where(
                m.KnowledgeDocument.profile_id == resume.profile_id,
                m.KnowledgeDocument.active.is_(True),
                m.KnowledgeDocument.kind == "personal",
                m.KnowledgeDocument.status == "CONTRADICTED",
            )
            .limit(1)
        )
        accepted = []
        text = old.text
        seen = set()
        for raw in result["proposal"]["edits"]:
            edit = s.Edit.model_validate(raw)
            ok, why = check_edit(
                edit, claims.get(edit.claim_id), evidence, audits.get(edit.claim_id, {})
            )
            if conflict:
                ok = False
                why = "Resolve contradicted personal knowledge in this profile before applying automatic resume changes"
            if edit.claim_id in seen or text.count(edit.previous_text) != 1:
                ok = False
                why = "Duplicate or ambiguous claim replacement"
            seen.add(edit.claim_id)
            if ok:
                text = text.replace(edit.previous_text, edit.new_text, 1)
                accepted.append(edit)
            else:
                db.add(
                    m.CandidateConfirmation(
                        resume_id=resume.id,
                        iteration_id=it.id,
                        question=f"Confirm or correct proposed wording: {edit.new_text}\nReason held: {why}",
                    )
                )
            await event(
                db,
                it.id,
                "resume",
                "edit_accepted" if ok else "edit_rejected",
                {"edit": raw, "reason": why},
            )
        if not accepted or text == old.text:
            await event(
                db,
                it.id,
                "resume",
                "no_supported_changes",
                {"message": "Preserved current version; no supported revision."},
            )
            return
        version = await create_version(db, resume, text, reason)
        # Preserve supported statuses and provenance for unchanged claims, and accepted spans.
        newclaims = await rows(db, m.Claim, version_id=version.id)
        for new in newclaims:
            matched = next((e for e in accepted if e.new_text == new.text), None)
            prior = next((c for c in claims.values() if c.text == new.text), None)
            if matched:
                new.status = (
                    "VERIFIED"
                    if all(
                        evidence[x].status == "VERIFIED" for x in matched.evidence_ids
                    )
                    else "CANDIDATE_CONFIRMED"
                )
                new.warning = ""
                for eid in matched.evidence_ids:
                    db.add(m.ClaimEvidenceLink(claim_id=new.id, evidence_id=eid))
            elif prior:
                new.status = prior.status
                new.warning = prior.warning
                for link in await rows(db, m.ClaimEvidenceLink, claim_id=prior.id):
                    db.add(
                        m.ClaimEvidenceLink(
                            claim_id=new.id, evidence_id=link.evidence_id
                        )
                    )
        version.submission_ready = all(
            c.status in {"VERIFIED", "CANDIDATE_CONFIRMED"} for c in newclaims
        )
        for edit in accepted:
            db.add(
                m.Revision(
                    iteration_id=it.id,
                    version_id=version.id,
                    previous_text=edit.previous_text,
                    new_text=edit.new_text,
                    reason=edit.reason,
                    evidence_ids=edit.evidence_ids,
                    agent="resume",
                    audit=audits[edit.claim_id],
                )
            )
        it.version_id = version.id
