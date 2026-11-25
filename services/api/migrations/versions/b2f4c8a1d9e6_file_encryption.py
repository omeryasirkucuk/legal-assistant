"""Track which file payloads have been encrypted.

Revision ID: b2f4c8a1d9e6
Revises: ea2d6f91b0c4
"""

import sqlalchemy as sa
from alembic import op

revision = "b2f4c8a1d9e6"
down_revision = "ea2d6f91b0c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stored_files", sa.Column("encrypted", sa.Boolean(), nullable=False,
                                            server_default=sa.false()))


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM stored_files WHERE encrypted LIMIT 1")).scalar():
        raise RuntimeError("cannot downgrade a store that contains encrypted files")
    op.drop_column("stored_files", "encrypted")
