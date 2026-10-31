"""Stored files: user attachments and files made for them (petitions).

Revision ID: e5f9c3d7b2a4
Revises: d4e8b2c6a1f3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5f9c3d7b2a4"
down_revision = "d4e8b2c6a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "stored_files",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("chat_id", uuid, sa.ForeignKey("chats.id", ondelete="SET NULL"), index=True),
        sa.Column("message_id", uuid, sa.ForeignKey("messages.id", ondelete="SET NULL"),
                  index=True),
        sa.Column("draft_id", uuid, sa.ForeignKey("drafts.id", ondelete="CASCADE"), index=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("stored_files")
