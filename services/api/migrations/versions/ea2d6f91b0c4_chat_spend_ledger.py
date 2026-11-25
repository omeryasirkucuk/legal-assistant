"""Backfill the spend ledger from existing assistant messages.

Revision ID: ea2d6f91b0c4
Revises: a7c3e9f1b2d5
"""

from alembic import op

revision = "ea2d6f91b0c4"
down_revision = "a7c3e9f1b2d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy details have no timestamp of their own, so use their message's timestamp.
    op.execute("""
        INSERT INTO llm_spend (id, user_id, purpose, cost_usd, created_at)
        SELECT gen_random_uuid(), chats.user_id, costs.purpose, costs.amount, messages.created_at
        FROM messages
        JOIN chats ON chats.id = messages.chat_id
        CROSS JOIN LATERAL (VALUES
            ('chat_answer', CASE WHEN jsonb_typeof(messages.meta -> 'cost_usd') = 'number'
                                  THEN (messages.meta ->> 'cost_usd')::double precision END),
            ('chat_detail', CASE WHEN jsonb_typeof(messages.meta -> 'detail_cost_usd') = 'number'
                                  THEN (messages.meta ->> 'detail_cost_usd')::double precision END)
        ) AS costs(purpose, amount)
        WHERE messages.role = 'assistant' AND costs.amount > 0
    """)


def downgrade() -> None:
    op.execute("DELETE FROM llm_spend WHERE purpose IN ('chat_answer', 'chat_detail')")
