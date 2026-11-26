"""Add personal and case-linked calendar events.

Revision ID: f7e33b91c842
Revises: b2f4c8a1d9e6
"""

import sqlalchemy as sa
from alembic import op

revision = "f7e33b91c842"
down_revision = "b2f4c8a1d9e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.Uuid(), sa.ForeignKey("matters.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("due", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time()),
        sa.Column("end_time", sa.Time()),
        sa.Column("location", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("reminder_minutes", sa.Integer()),
        sa.Column("remind_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_dismissed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_calendar_events_user_due", "calendar_events", ["user_id", "due"])
    op.create_index("ix_calendar_events_matter_id", "calendar_events", ["matter_id"])


def downgrade() -> None:
    op.drop_table("calendar_events")
