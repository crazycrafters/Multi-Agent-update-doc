"""Normalized audit records; JSON fields hold versioned structured agent messages."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, JSON, DateTime, Integer, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass
class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class User(Record, Base):
    __tablename__ = 'users'
    name: Mapped[str] = mapped_column(default='Local candidate')

class Resume(Record, Base):
    __tablename__ = 'resumes'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str]
    original_text: Mapped[str] = mapped_column(Text)
    target_role: Mapped[str] = mapped_column(Text)
    job_description: Mapped[str] = mapped_column(Text, default="")
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

class ResumeVersion(Record, Base):
    __tablename__ = 'resume_versions'
    __table_args__ = (UniqueConstraint('resume_id','number'),)
    resume_id: Mapped[str] = mapped_column(ForeignKey('resumes.id'))
    number: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    submission_ready: Mapped[bool] = mapped_column(default=False)

class Project(Record, Base):
    __tablename__ = 'projects'
    resume_id: Mapped[str] = mapped_column(ForeignKey('resumes.id'))
    name: Mapped[str]

class EvidenceRecord(Record, Base):
    __tablename__ = 'evidence_records'
    resume_id: Mapped[str] = mapped_column(ForeignKey('resumes.id'))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default='UNVERIFIED')
    kind: Mapped[str] = mapped_column(default='candidate_note')

class Claim(Record, Base):
    __tablename__ = 'claims'
    version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default='UNVERIFIED')
    warning: Mapped[str] = mapped_column(Text, default='')

class ResumeBullet(Record, Base):
    __tablename__ = 'resume_bullets'
    version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))
    claim_id: Mapped[str | None] = mapped_column(ForeignKey('claims.id'), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int]

class ClaimEvidenceLink(Record, Base):
    __tablename__ = 'claim_evidence_links'
    claim_id: Mapped[str] = mapped_column(ForeignKey('claims.id'))
    evidence_id: Mapped[str] = mapped_column(ForeignKey('evidence_records.id'))

class MetricEvidence(Record, Base):
    __tablename__ = 'metric_evidence'
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    metric_name: Mapped[str]
    metric_definition: Mapped[str] = mapped_column(Text)
    numerator: Mapped[float | None] = mapped_column(nullable=True)
    denominator: Mapped[float | None] = mapped_column(nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(nullable=True)
    final_value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str]
    sample_size: Mapped[int | None] = mapped_column(nullable=True)
    observation_window: Mapped[str]
    workload_description: Mapped[str]
    hardware_configuration: Mapped[str]
    concurrency: Mapped[int | None] = mapped_column(nullable=True)
    model_configuration: Mapped[str]
    measurement_method: Mapped[str]
    source_reference: Mapped[str]
    evidence_status: Mapped[str] = mapped_column(default='UNVERIFIED')
    limitations: Mapped[str] = mapped_column(Text, default='')
    relationship: Mapped[str] = mapped_column(default='correlation')

class Iteration(Record, Base):
    __tablename__ = 'iterations'
    __table_args__ = (UniqueConstraint('resume_id','number'),)
    resume_id: Mapped[str] = mapped_column(ForeignKey('resumes.id'))
    version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))
    output_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    number: Mapped[int]
    state: Mapped[str] = mapped_column(default='IDLE')
    paused: Mapped[bool] = mapped_column(default=False)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    research_consent: Mapped[bool] = mapped_column(default=False)
    provider_consent: Mapped[bool] = mapped_column(default=False)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

class InterviewSession(Record, Base):
    __tablename__ = 'interview_sessions'
    iteration_id: Mapped[str] = mapped_column(ForeignKey('iterations.id'), unique=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))

class InterviewQuestion(Record, Base):
    __tablename__ = 'interview_questions'
    __table_args__ = (UniqueConstraint('session_id','number','followup'),)
    session_id: Mapped[str] = mapped_column(ForeignKey('interview_sessions.id'))
    number: Mapped[int]
    followup: Mapped[bool] = mapped_column(default=False)
    text: Mapped[str] = mapped_column(Text)
    claim_ids: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(default='senior')

class InterviewAnswer(Record, Base):
    __tablename__ = 'interview_answers'
    question_id: Mapped[str] = mapped_column(ForeignKey('interview_questions.id'), unique=True)
    text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(default='simulated')
    limitations: Mapped[list] = mapped_column(JSON, default=list)

class InterviewEvaluation(Record, Base):
    __tablename__ = 'interview_evaluations'
    question_id: Mapped[str] = mapped_column(ForeignKey('interview_questions.id'), unique=True)
    scores: Mapped[dict] = mapped_column(JSON)
    weaknesses: Mapped[list] = mapped_column(JSON)
    followup: Mapped[str | None] = mapped_column(Text, nullable=True)

class WeaknessReport(Record, Base):
    __tablename__ = 'weakness_reports'
    iteration_id: Mapped[str] = mapped_column(ForeignKey('iterations.id'), unique=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('interview_sessions.id'))
    report: Mapped[dict] = mapped_column(JSON)

class ResearchSource(Record, Base):
    __tablename__ = 'research_sources'
    iteration_id: Mapped[str] = mapped_column(ForeignKey('iterations.id'))
    title: Mapped[str]
    url: Mapped[str] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(nullable=True)
    access_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class ResearchFinding(Record, Base):
    __tablename__ = 'research_findings'
    source_id: Mapped[str] = mapped_column(ForeignKey('research_sources.id'))
    details: Mapped[dict] = mapped_column(JSON)

class Revision(Record, Base):
    __tablename__ = 'revisions'
    iteration_id: Mapped[str | None] = mapped_column(ForeignKey('iterations.id'), nullable=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('resume_versions.id'))
    previous_text: Mapped[str] = mapped_column(Text)
    new_text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON)
    agent: Mapped[str]
    audit: Mapped[dict] = mapped_column(JSON)

class CandidateConfirmation(Record, Base):
    __tablename__ = 'candidate_confirmations'
    resume_id: Mapped[str] = mapped_column(ForeignKey('resumes.id'))
    iteration_id: Mapped[str | None] = mapped_column(ForeignKey('iterations.id'), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey('evidence_records.id'), nullable=True)

class AgentExecution(Record, Base):
    __tablename__ = 'agent_executions'
    iteration_id: Mapped[str] = mapped_column(ForeignKey('iterations.id'))
    agent: Mapped[str]
    task: Mapped[str]
    model: Mapped[str]
    status: Mapped[str] = mapped_column(default='running')
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)

class AgentEvent(Base):
    __tablename__ = 'agent_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[str] = mapped_column(ForeignKey('iterations.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    agent: Mapped[str]
    kind: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON)
