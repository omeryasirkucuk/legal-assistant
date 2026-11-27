"""Keep submitted problem reports and their conversation snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a3282fd12b90"
down_revision = "d548c17ab930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problem_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("context", JSONB(), nullable=False),
    )
    op.create_index("ix_problem_reports_created_at", "problem_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("problem_reports")
