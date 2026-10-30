"""Separate target profiles, pgvector knowledge and workspace settings."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
import uuid

revision = "d32f91c6a501"
down_revision = "c21a98b7d004"
branch_labels = None
depends_on = None


def record():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    pg = op.get_bind().dialect.name == "postgresql"
    if pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "profiles",
        *record(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_role", sa.Text(), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
    )
    with op.batch_alter_table("resumes") as b:
        b.add_column(sa.Column("profile_id", sa.String(36), nullable=True))
    conn = op.get_bind()
    for row in conn.execute(
        sa.text("SELECT id,target_role,job_description,created_at FROM resumes")
    ).mappings():
        pid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO profiles (id,created_at,name,target_role,job_description) VALUES (:id,:created,:name,:role,:jd)"
            ),
            {
                "id": pid,
                "created": row["created_at"],
                "name": row["target_role"][:120],
                "role": row["target_role"],
                "jd": row["job_description"],
            },
        )
        conn.execute(
            sa.text("UPDATE resumes SET profile_id=:pid WHERE id=:id"),
            {"pid": pid, "id": row["id"]},
        )
    with op.batch_alter_table("resumes") as b:
        b.alter_column("profile_id", existing_type=sa.String(36), nullable=False)
        b.create_foreign_key("fk_resumes_profile", "profiles", ["profile_id"], ["id"])
        b.create_index("ix_resumes_profile_id", ["profile_id"])
    with op.batch_alter_table("iterations") as b:
        b.add_column(sa.Column("run_id", sa.String(36), nullable=True))
        b.add_column(
            sa.Column("run_step", sa.Integer(), nullable=False, server_default="1")
        )
        b.add_column(
            sa.Column(
                "planned_iterations", sa.Integer(), nullable=False, server_default="1"
            )
        )
    op.execute("UPDATE iterations SET run_id=id")
    with op.batch_alter_table("iterations") as b:
        b.alter_column("run_id", existing_type=sa.String(36), nullable=False)
    op.create_table(
        "workspace_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_table(
        "knowledge_documents",
        *record(),
        sa.Column(
            "profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_knowledge_documents_profile_id", "knowledge_documents", ["profile_id"]
    )
    op.create_table(
        "knowledge_chunks",
        *record(),
        sa.Column(
            "profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536) if pg else sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_knowledge_chunks_profile_id", "knowledge_chunks", ["profile_id"]
    )
    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"]
    )
    if pg:
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks USING gin (to_tsvector('english', text))"
        )
    with op.batch_alter_table("evidence_records") as b:
        b.add_column(sa.Column("knowledge_document_id", sa.String(36), nullable=True))
        b.create_foreign_key(
            "fk_evidence_knowledge",
            "knowledge_documents",
            ["knowledge_document_id"],
            ["id"],
        )
    op.create_table(
        "embedding_usage",
        *record(),
        sa.Column(
            "profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("evidence_records") as b:
        b.drop_constraint("fk_evidence_knowledge", type_="foreignkey")
        b.drop_column("knowledge_document_id")
    op.drop_table("embedding_usage")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("workspace_settings")
    with op.batch_alter_table("iterations") as b:
        b.drop_column("run_id")
        b.drop_column("run_step")
        b.drop_column("planned_iterations")
    with op.batch_alter_table("resumes") as b:
        b.drop_index("ix_resumes_profile_id")
        b.drop_constraint("fk_resumes_profile", type_="foreignkey")
        b.drop_column("profile_id")
    op.drop_table("profiles")
