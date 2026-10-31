"""What each of the lawyer's sample petitions is, as read by the model.

Revision ID: b8c3f6a1e7d2
Revises: a7b2e5f9d4c6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8c3f6a1e7d2"
down_revision = "a7b2e5f9d4c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Samples kept earlier are read when the list is next opened (api/drafting.py).
    op.add_column("style_samples", sa.Column("profile", postgresql.JSONB(), nullable=False,
                                             server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("style_samples", "profile")
