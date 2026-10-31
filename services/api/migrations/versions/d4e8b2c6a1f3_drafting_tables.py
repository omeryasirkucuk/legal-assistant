"""Style samples, style profiles and drafts for petition drafting.

Revision ID: d4e8b2c6a1f3
Revises: c3d9a7e1f2b4
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "d4e8b2c6a1f3"
down_revision = "c3d9a7e1f2b4"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.create_table(
        "style_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("petition_type", sa.String(40)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("style", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(16), nullable=False, server_default="upload"),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table(
        "style_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table(
        "drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chats.id", ondelete="SET NULL"), index=True),
        sa.Column("petition_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("drafts")
    op.drop_table("style_profiles")
    op.drop_table("style_samples")
