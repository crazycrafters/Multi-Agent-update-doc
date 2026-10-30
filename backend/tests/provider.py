"""Deterministic provider confined to automated tests."""

import asyncio
from app.agents import Result
from app import schemas as s


class TestProvider:
    __test__ = False

    def __init__(self):
        self.calls = []
        self.fail = False
        self.gate = None
        self.entered = asyncio.Event()

    def model(self, agent):
        return "test-only"

    async def generate(
        self, agent, task, context, schema, on_snapshot=None, scope=None
    ):
        self.calls.append((agent, task, context))
        self.entered.set()
        if self.gate:
            await self.gate.wait()
        if self.fail:
            raise ConnectionError("test failure")
        claim = (context.get("claims") or [{}])[0]
        if schema == s.Analysis:
            data = {
                "summary": "Gaps",
                "target_alignment": context["target_role"],
                "claims": [],
                "confirmation_questions": ["What did you implement?"],
            }
        elif schema == s.Proposal:
            evidence = context["evidence"]
            edits = []
            if evidence:
                edits = [
                    dict(
                        claim_id=claim["id"],
                        previous_text=claim["text"],
                        new_text=evidence[0]["text"],
                        reason="Supported detail",
                        evidence_ids=[evidence[0]["id"]],
                    )
                ]
            data = {
                "edits": edits,
                "study_recommendations": ["Study validation"],
                "summary": "Revision",
            }
        elif schema == s.Audit:
            data = {
                "items": [
                    dict(
                        claim_id=e["claim_id"], verdict="PASS", reason="Confirmed span"
                    )
                    for e in context["proposal"]["edits"]
                ]
            }
        elif schema == s.Question:
            data = {
                "text": f"For {context['target_role']}, explain ownership after {len(context['transcript'])} answers",
                "claim_ids": [claim["id"]],
                "difficulty": "target-role",
            }
        elif schema == s.Answer:
            data = {
                "text": "I can confirm only supplied evidence. A proposed design would require validation.",
                "limitations": ["Missing measurements"],
                "claim_ids": [claim.get("id", "")],
            }
        elif schema == s.Evaluation:
            data = {
                "scores": {
                    k: {"value": 3, "reason": "No measurements supplied"}
                    for k in s.Scores.model_fields
                },
                "weaknesses": [
                    dict(
                        claim_ids=[claim["id"]],
                        weakness="Missing validation",
                        severity="high",
                        required_evidence=["Test report"],
                        research_topics=["validation methods"],
                    )
                ],
                "followup": None
                if "follow-up" in task
                else "How would you validate the hypothetical design?",
            }
        elif schema == s.Feedback:
            data = {k: [] for k in s.Feedback.model_fields}
            data.update(
                research_topics=["validation methods"],
                confirmation_questions=["What validation actually ran?"],
            )
        elif schema == s.ResearchNotes:
            data = {
                "findings": [
                    dict(
                        source_url="https://docs.python.org/3/library/asyncio.html",
                        technical_findings="Structured concurrency",
                        applicable_architecture="Async workflows",
                        implementation_tradeoffs="Cancellation boundaries",
                        relevant_metrics="No personal metrics",
                        limitations="Public context",
                        relationship_to_claim="Preparation only",
                    )
                ],
                "study_recommendations": ["Read documentation"],
            }
        else:
            raise AssertionError(schema)
        if on_snapshot:
            await on_snapshot(data["text"][:40])
            await on_snapshot(data["text"])
        return Result(schema.model_validate(data).model_dump(mode="json"), 100, 50)

    async def research(self, topics, scope=None):
        self.calls.append(("resume", "research", {"topics": topics}))
        return Result(
            {
                "text": "Public documentation",
                "sources": [
                    {
                        "title": "asyncio documentation",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                    }
                ],
            },
            100,
            50,
            1,
        )
