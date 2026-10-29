"""any_terms full-text helper

Revision ID: 4e6355300f2a
Revises: 0ce6f2411f03
Create Date: 2026-10-29 22:49:24.318830

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4e6355300f2a'
down_revision: str | Sequence[str] | None = '0ce6f2411f03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # OR-semantics tsquery: the stemmed terms of plainto_tsquery joined with | instead of &.
    op.execute("""
        CREATE OR REPLACE FUNCTION any_terms(config regconfig, query text) RETURNS tsquery
        LANGUAGE sql IMMUTABLE STRICT AS $$
            SELECT CASE WHEN plainto_tsquery(config, query)::text = '' THEN ''::tsquery
                   ELSE replace(plainto_tsquery(config, query)::text, ' & ', ' | ')::tsquery END
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS any_terms(regconfig, text)")
