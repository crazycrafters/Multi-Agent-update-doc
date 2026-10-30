from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, SecretStr


class Status(StrEnum):
    VERIFIED = "VERIFIED"
    CANDIDATE_CONFIRMED = "CANDIDATE_CONFIRMED"
    PUBLIC_CONTEXT = "PUBLIC_CONTEXT"
    PROPOSED = "PROPOSED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"


class State(StrEnum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    RESUME_ANALYSIS = "RESUME_ANALYSIS"
    RESUME_DRAFTING = "RESUME_DRAFTING"
    INTERVIEW_PREPARATION = "INTERVIEW_PREPARATION"
    INTERVIEWING = "INTERVIEWING"
    INTERVIEW_EVALUATION = "INTERVIEW_EVALUATION"
    RESEARCHING = "RESEARCHING"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"
    RESUME_REVISION = "RESUME_REVISION"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimData(Strict):
    text: str
    evidence_ids: list[str]
    status: Status
    warning: str


class Analysis(Strict):
    summary: str
    target_alignment: str
    claims: list[ClaimData]
    confirmation_questions: list[str]


class Question(Strict):
    text: str
    claim_ids: list[str]
    difficulty: str


class Answer(Strict):
    knowledge_ids: list[str]
    text: str
    limitations: list[str]
    claim_ids: list[str]


class Score(Strict):
    value: int = Field(ge=0, le=10)
    reason: str


class Scores(Strict):
    technical_correctness: Score
    implementation_depth: Score
    ownership_clarity: Score
    evidence_strength: Score
    reliability_understanding: Score
    measurement_quality: Score
    communication_clarity: Score


class Weakness(Strict):
    claim_ids: list[str]
    weakness: str
    severity: Literal["low", "medium", "high"]
    required_evidence: list[str]
    research_topics: list[str]


class Evaluation(Strict):
    scores: Scores
    weaknesses: list[Weakness]
    followup: str | None


class Feedback(Strict):
    strong_answers: list[str]
    weak_answers: list[str]
    unsupported_claims: list[str]
    contradictions: list[str]
    missing_details: list[str]
    knowledge_gaps: list[str]
    claims_to_narrow: list[str]
    weaknesses: list[Weakness]
    research_topics: list[str]
    confirmation_questions: list[str]


class Edit(Strict):
    claim_id: str
    previous_text: str
    new_text: str
    reason: str
    evidence_ids: list[str]


class Proposal(Strict):
    edits: list[Edit]
    study_recommendations: list[str]
    summary: str


class AuditItem(Strict):
    claim_id: str
    verdict: Literal["PASS", "REVISE", "HOLD", "REMOVE"]
    reason: str


class Audit(Strict):
    items: list[AuditItem]


class Finding(Strict):
    source_url: str
    technical_findings: str
    applicable_architecture: str
    implementation_tradeoffs: str
    relevant_metrics: str
    limitations: str
    relationship_to_claim: str


class ResearchNotes(Strict):
    findings: list[Finding]
    study_recommendations: list[str]


class StartRequest(Strict):
    iteration_count: int = Field(default=1, ge=1, le=100)
    embedding_consent: bool = False
    provider_consent: bool = False
    research_consent: bool = False


class EditRequest(Strict):
    text: str = Field(min_length=1, max_length=100000)
    reason: str = Field(min_length=1, max_length=2000)


class EvidenceRequest(Strict):
    text: str = Field(min_length=1, max_length=20000)
    source: str = Field(min_length=1, max_length=2000)
    kind: Literal["candidate_note", "direct_artifact"] = "candidate_note"


class ConfirmRequest(Strict):
    response: str = Field(min_length=1, max_length=20000)


class MetricRequest(Strict):
    project_name: str
    metric_name: Literal[
        "Evaluation-job failure rate",
        "p50 latency",
        "p95 latency",
        "p99 latency",
        "Job throughput",
        "Successful cases per minute",
        "Validation correctness",
        "Retrieval recall@k",
        "Retrieval precision@k",
        "Hallucination rate",
        "Answer correctness",
        "Cost per successful evaluation",
    ]
    metric_definition: str
    numerator: float | None = None
    denominator: float | None = Field(default=None, gt=0)
    baseline_value: float | None = None
    final_value: float
    unit: str
    sample_size: int = Field(gt=0)
    observation_window: str = Field(min_length=1)
    workload_description: str = Field(min_length=1)
    hardware_configuration: str
    concurrency: int | None = Field(default=None, gt=0)
    model_configuration: str
    measurement_method: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    limitations: str
    relationship: Literal[
        "percentage_point_change",
        "relative_percentage_change",
        "absolute_change",
        "correlation",
        "causal_evidence",
    ]


class MetricReviewRequest(Strict):
    reviewed_direct_measurement: Literal[True]
    review_note: str = Field(min_length=10, max_length=5000)
    supported_statement: str = Field(min_length=1, max_length=2000)


class ProviderConnectionRequest(Strict):
    api_key: SecretStr = Field(min_length=1, max_length=1024)


class ProviderSelectRequest(Strict):
    provider: Literal["openai", "codex"]


class CodexResearchSource(Strict):
    url: str
    title: str


class CodexResearchResult(Strict):
    text: str
    sources: list[CodexResearchSource]


class ProfileRequest(Strict):
    name: str = Field(min_length=1, max_length=120)
    target_role: str = Field(min_length=1, max_length=500)
    job_description: str = Field(default="", max_length=30000)


class KnowledgeRequest(Strict):
    title: str = Field(min_length=1, max_length=200)
    project: str = Field(default="", max_length=200)
    kind: Literal["personal", "reference", "open_question"]
    status: Literal[
        "UNVERIFIED",
        "CANDIDATE_CONFIRMED",
        "PUBLIC_CONTEXT",
        "PROPOSED",
        "CONTRADICTED",
    ] = "UNVERIFIED"
    source: str = Field(min_length=1, max_length=2000)
    content: str = Field(min_length=1, max_length=100000)


class SearchRequest(Strict):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=12)
    semantic: bool = False
    embedding_consent: bool = False


class EmbeddingRequest(Strict):
    consent: bool = False


class AgentStrategies(Strict):
    resume: str = Field(default="", max_length=6000)
    interviewee: str = Field(default="", max_length=6000)
    interviewer: str = Field(default="", max_length=6000)


class WorkflowOptions(Strict):
    question_count: int = Field(default=10, ge=1, le=20)
    followups: bool = True
    initial_draft: bool = True
    research: bool = True
    semantic_retrieval: bool = False


class WorkspaceConfig(Strict):
    strategies: AgentStrategies = Field(default_factory=AgentStrategies)
    workflow: WorkflowOptions = Field(default_factory=WorkflowOptions)
    api_budget_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    search_usd_per_call: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    embedding_usd_per_million: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )


class ResumeStrategy(Strict):
    id: str
    title: str = Field(min_length=1, max_length=70)
    summary: str = Field(min_length=1, max_length=240)


class StrategyOptions(Strict):
    options: list[ResumeStrategy] = Field(min_length=2, max_length=4)


class StrategySelection(Strict):
    strategy_id: str
