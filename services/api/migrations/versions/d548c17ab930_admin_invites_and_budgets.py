"""Persist invitation history and per-account budgets."""

import sqlalchemy as sa
from alembic import op

revision = "d548c17ab930"
down_revision = "ab6e2d4c91f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("registration_invites", sa.Column("code_encrypted", sa.Text()))
    op.add_column("registration_invites", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("llm_connection_settings", sa.Column("model_write", sa.String(200)))
    op.add_column("users", sa.Column("daily_budget_usd", sa.Float()))
    op.add_column("users", sa.Column("monthly_budget_usd", sa.Float()))


def downgrade():
    op.drop_column("users", "monthly_budget_usd")
    op.drop_column("users", "daily_budget_usd")
    op.drop_column("llm_connection_settings", "model_write")
    op.drop_column("registration_invites", "expires_at")
    op.drop_column("registration_invites", "code_encrypted")
