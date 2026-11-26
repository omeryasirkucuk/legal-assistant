"""Track a per-account session version for password changes.

Revision ID: f1b7d49e3a62
Revises: b2f4c8a1d9e6
"""

import sqlalchemy as sa
from alembic import op

revision = "f1b7d49e3a62"
down_revision = "b2f4c8a1d9e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False,
                                     server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("users", "session_version")
