"""Trigram indexes for the sidebar history search (partial words, mid-word text).

The search compares Turkish-folded text with LIKE '%term%' (chat/history_search.py); these
expression indexes match that exact expression so it does not scan every message.

Revision ID: b7e4c1d2a9f0
Revises: 8fa129cb3b10
"""

from alembic import op

revision = "b7e4c1d2a9f0"
down_revision = "8fa129cb3b10"
branch_labels = None
depends_on = None

_FOLD = "lower(translate({col}, 'İI', 'iı'))"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_messages_content_trgm ON messages "
               f"USING gin (({_FOLD.format(col='content')}) gin_trgm_ops)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_chats_title_trgm ON chats "
               f"USING gin (({_FOLD.format(col='title')}) gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chats_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_messages_content_trgm")
