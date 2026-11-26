"""Add email-bound registration invitations.

Revision ID: ab6e2d4c91f8
Revises: f7e33b91c842
"""

import sqlalchemy as sa
from alembic import op

revision = "ab6e2d4c91f8"
down_revision = "f7e33b91c842"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registration_invites",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("registration_invites")
