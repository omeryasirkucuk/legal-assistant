"""Hybrid search over the local statute index (article level), plus exact article lookup.

This is what lets the system find the provisions a question depends on without relying on
the model already knowing their numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from legal_api.embeddings import embed_query
from legal_api.retrieval.hybrid import fuse
from legal_api.sources.bedesten_statutes import parse_article_label

CANDIDATES = 40

_FTS_SQL = """
SELECT id FROM statute_articles
WHERE tsv @@ any_terms('turkish', $1)
ORDER BY ts_rank_cd(tsv, any_terms('turkish', $1)) DESC
LIMIT $2
"""
_VECTOR_SQL = "SELECT id FROM statute_articles ORDER BY embedding <=> $1 LIMIT $2"
_ROWS_SQL = """
SELECT id, law_number, law_title, statute_id, kind, label, heading, text, url, fetched_at
FROM statute_articles WHERE id = ANY($1::int[])
"""


@dataclass(frozen=True)
class StatuteHit:
    id: int
    law_number: str
    law_title: str
    statute_id: str
    label: str
    heading: str
    text: str
    url: str
    fetched_at: datetime
    score: float = 0.0


def _hit(row: asyncpg.Record, score: float = 0.0) -> StatuteHit:
    return StatuteHit(row["id"], row["law_number"], row["law_title"], row["statute_id"],
                      row["label"], row["heading"], row["text"], row["url"], row["fetched_at"],
                      score)


async def search_statutes(conn: asyncpg.Connection, query: str, limit: int = 10,
                          laws: list[str] | None = None) -> list[StatuteHit]:
    fts = [r["id"] for r in await conn.fetch(_FTS_SQL, query, CANDIDATES)]
    vec = [r["id"] for r in await conn.fetch(_VECTOR_SQL, embed_query(query), CANDIDATES)]
    scores = fuse([fts, vec])
    rows = {r["id"]: r for r in await conn.fetch(_ROWS_SQL, list(scores))}
    hits = [_hit(rows[i], s) for i, s in sorted(scores.items(), key=lambda kv: -kv[1])]
    if laws:
        hits = [h for h in hits if h.law_number in laws]
    return hits[:limit]


async def find_law(conn: asyncpg.Connection, law: str) -> str | None:
    """Law number for a number or a (partial) official name, if the law is indexed."""
    law = law.strip()
    if law.isdigit():
        found = await conn.fetchval(
            "SELECT law_number FROM statute_articles WHERE law_number = $1 LIMIT 1", law)
        return found
    return await conn.fetchval(
        "SELECT law_number FROM statute_articles WHERE law_title ILIKE '%' || $1 || '%' "
        "LIMIT 1", law)


async def get_article(conn: asyncpg.Connection, law: str, label: str) -> StatuteHit | None:
    """Exact article from the index; None if the law isn't indexed or has no such article."""
    number = await find_law(conn, law)
    ref = parse_article_label(str(label))
    if number is None or ref is None:
        return None
    kind, _, display = ref
    row = await conn.fetchrow(
        _ROWS_SQL.replace("WHERE id = ANY($1::int[])",
                          "WHERE law_number = $1 AND kind = $2 AND label = $3"),
        number, kind, display)
    return _hit(row) if row else None
