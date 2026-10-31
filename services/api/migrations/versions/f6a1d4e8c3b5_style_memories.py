"""Style memories (preferences learnt from the lawyer's edits) and sample meaning vectors.

Revision ID: f6a1d4e8c3b5
Revises: e5f9c3d7b2a4
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "f6a1d4e8c3b5"
down_revision = "e5f9c3d7b2a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "style_memories",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("petition_type", sa.String(40)),
        sa.Column("seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding", Vector(384)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("style_memories")
