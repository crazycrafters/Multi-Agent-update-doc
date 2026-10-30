from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Status(StrEnum):
    VERIFIED='VERIFIED'
    CANDIDATE_CONFIRMED='CANDIDATE_CONFIRMED'
    PUBLIC_CONTEXT='PUBLIC_CONTEXT'
    PROPOSED='PROPOSED'
    UNVERIFIED='UNVERIFIED'
    CONTRADICTED='CONTRADICTED'

class State(StrEnum):
    IDLE='IDLE'
    INITIALIZING='INITIALIZING'
    RESUME_ANALYSIS='RESUME_ANALYSIS'
    RESUME_DRAFTING='RESUME_DRAFTING'
    INTERVIEW_PREPARATION='INTERVIEW_PREPARATION'
    INTERVIEWING='INTERVIEWING'
    INTERVIEW_EVALUATION='INTERVIEW_EVALUATION'
    RESEARCHING='RESEARCHING'
    EVIDENCE_VALIDATION='EVIDENCE_VALIDATION'
    RESUME_REVISION='RESUME_REVISION'
    AWAITING_APPROVAL='AWAITING_APPROVAL'
    COMPLETED='COMPLETED'
    FAILED='FAILED'
    CANCELLED='CANCELLED'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

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
    text: str
    limitations: list[str]
    claim_ids: list[str]

class Score(Strict):
    value: int = Field(ge=0,le=10)
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
    severity: Literal['low','medium','high']
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
    verdict: Literal['PASS','REVISE','HOLD','REMOVE']
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
    provider_consent: bool = False
    research_consent: bool = False

class EditRequest(Strict):
    text: str = Field(min_length=1,max_length=100000)
    reason: str = Field(min_length=1,max_length=2000)

class EvidenceRequest(Strict):
    text: str = Field(min_length=1,max_length=20000)
    source: str = Field(min_length=1,max_length=2000)
    kind: Literal['candidate_note','direct_artifact'] = 'candidate_note'

class ConfirmRequest(Strict):
    response: str = Field(min_length=1,max_length=20000)

class MetricRequest(Strict):
    project_name: str
    metric_name: Literal['Evaluation-job failure rate','p50 latency','p95 latency','p99 latency','Job throughput','Successful cases per minute','Validation correctness','Retrieval recall@k','Retrieval precision@k','Hallucination rate','Answer correctness','Cost per successful evaluation']
    metric_definition: str
    numerator: float | None = None
    denominator: float | None = Field(default=None,gt=0)
    baseline_value: float | None = None
    final_value: float
    unit: str
    sample_size: int = Field(gt=0)
    observation_window: str = Field(min_length=1)
    workload_description: str = Field(min_length=1)
    hardware_configuration: str
    concurrency: int | None = Field(default=None,gt=0)
    model_configuration: str
    measurement_method: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    limitations: str
    relationship: Literal['percentage_point_change','relative_percentage_change','absolute_change','correlation','causal_evidence']

class MetricReviewRequest(Strict):
    reviewed_direct_measurement: Literal[True]
    review_note: str = Field(min_length=10,max_length=5000)
    supported_statement: str = Field(min_length=1,max_length=2000)
