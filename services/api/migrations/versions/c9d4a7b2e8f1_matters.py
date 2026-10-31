"""Case files (matters) with their deadlines; chats and files can belong to one.

Revision ID: c9d4a7b2e8f1
Revises: b8c3f6a1e7d2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9d4a7b2e8f1"
down_revision = "b8c3f6a1e7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "matters",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client", sa.String(200), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("opponent", sa.String(200), nullable=False, server_default=""),
        sa.Column("court", sa.String(200), nullable=False, server_default=""),
        sa.Column("case_no", sa.String(100), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, index=True))
    op.create_table(
        "matter_deadlines",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("matter_id", uuid, sa.ForeignKey("matters.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("due", sa.Date(), nullable=False, index=True),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("message_id", uuid, sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for table in ("chats", "stored_files"):
        op.add_column(table, sa.Column("matter_id", uuid,
                                       sa.ForeignKey("matters.id", ondelete="SET NULL")))
        op.create_index(f"ix_{table}_matter_id", table, ["matter_id"])


def downgrade() -> None:
    for table in ("chats", "stored_files"):
        op.drop_index(f"ix_{table}_matter_id", table)
        op.drop_column(table, "matter_id")
    op.drop_table("matter_deadlines")
    op.drop_table("matters")
