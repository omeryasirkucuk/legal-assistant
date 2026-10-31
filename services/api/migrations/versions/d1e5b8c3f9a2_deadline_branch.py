"""A deadline's branch of law (civil, criminal, enforcement, administrative, arbitration).

Revision ID: d1e5b8c3f9a2
Revises: c9d4a7b2e8f1
"""

import sqlalchemy as sa
from alembic import op

revision = "d1e5b8c3f9a2"
down_revision = "c9d4a7b2e8f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matter_deadlines", sa.Column("branch", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("matter_deadlines", "branch")
