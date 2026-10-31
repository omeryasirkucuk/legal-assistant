"""Kind and area labels on stored files, for filtering the lawyer's files.

Revision ID: a7b2e5f9d4c6
Revises: f6a1d4e8c3b5
"""

import sqlalchemy as sa
from alembic import op

revision = "a7b2e5f9d4c6"
down_revision = "f6a1d4e8c3b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing files are labelled when the file list is next opened (api/files.py).
    op.add_column("stored_files", sa.Column("kind", sa.String(32)))
    op.add_column("stored_files", sa.Column("area", sa.String(32)))


def downgrade() -> None:
    op.drop_column("stored_files", "area")
    op.drop_column("stored_files", "kind")
