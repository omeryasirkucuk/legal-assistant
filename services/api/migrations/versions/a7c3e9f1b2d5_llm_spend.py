"""Model spend outside chat answers, for the daily budget.

Revision ID: a7c3e9f1b2d5
Revises: e2f6c9d4a1b7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7c3e9f1b2d5"
down_revision = "e2f6c9d4a1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "llm_spend",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("llm_spend")
