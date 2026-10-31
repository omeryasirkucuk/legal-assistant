"""Section path of each statute article (the parts and chapters it sits in).

Revision ID: c3d9a7e1f2b4
Revises: b7e4c1d2a9f0
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d9a7e1f2b4"
down_revision = "b7e4c1d2a9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("statute_articles",
                  sa.Column("section", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("statute_articles", "section")
