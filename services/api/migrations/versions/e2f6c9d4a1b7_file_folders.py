"""Folders in My files, and a file's folder.

Revision ID: e2f6c9d4a1b7
Revises: d1e5b8c3f9a2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e2f6c9d4a1b7"
down_revision = "d1e5b8c3f9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "file_folders",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("parent_id", uuid, sa.ForeignKey("file_folders.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("stored_files", sa.Column(
        "folder_id", uuid, sa.ForeignKey("file_folders.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_stored_files_folder_id", "stored_files", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_stored_files_folder_id", table_name="stored_files")
    op.drop_column("stored_files", "folder_id")
    op.drop_table("file_folders")
