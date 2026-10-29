"""Encrypted, administrator-managed LLM connection settings.

Revision ID: 8fa129cb3b10
Revises: 4e6355300f2a
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8fa129cb3b10"
down_revision: str | Sequence[str] | None = "4e6355300f2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(),
                                      nullable=False))
    # Make the first existing account the administrator so existing local installs retain
    # access to provider configuration after this migration.
    op.execute("""
        UPDATE users SET is_admin = true
        WHERE id = (SELECT id FROM users ORDER BY created_at, id LIMIT 1)
    """)
    op.create_table(
        "llm_connection_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("model_main", sa.String(200), nullable=False),
        sa.Column("model_draft", sa.String(200), nullable=False),
        sa.Column("model_cheap", sa.String(200), nullable=False),
        sa.Column("model_judge", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_llm_connection_settings_singleton"),
    )


def downgrade() -> None:
    op.drop_table("llm_connection_settings")
    op.drop_column("users", "is_admin")
