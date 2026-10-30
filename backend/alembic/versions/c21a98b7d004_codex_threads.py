"""Pin iterations to a provider and persist separate Codex agent threads."""

from alembic import op
import sqlalchemy as sa

revision = "c21a98b7d004"
down_revision = "ffb9c39110bd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "iterations",
        sa.Column("provider", sa.String(), nullable=False, server_default="openai"),
    )
    op.create_table(
        "provider_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "iteration_id",
            sa.String(36),
            sa.ForeignKey("iterations.id"),
            nullable=False,
        ),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.UniqueConstraint("iteration_id", "agent", "channel"),
    )


def downgrade():
    op.drop_table("provider_threads")
    op.drop_column("iterations", "provider")
