"""Persist retrieved knowledge citations with simulated answers."""

from alembic import op
import sqlalchemy as sa

revision = "e43c12b7d901"
down_revision = "d32f91c6a501"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "interview_answers",
        sa.Column("knowledge_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    with op.batch_alter_table("interview_answers") as b:
        b.drop_column("knowledge_ids")
