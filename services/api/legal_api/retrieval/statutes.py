"""Hybrid search over the local statute index (article level), plus exact article lookup.

This is what lets the system find the provisions a question depends on without relying on
the model already knowing their numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from legal_api.embeddings import embed_query
from legal_api.grounding.normalize import tr_fold
from legal_api.locale import law_abbreviations
from legal_api.retrieval.hybrid import fuse
from legal_api.retrieval.references import name_match
from legal_api.sources.bedesten_statutes import parse_article_label

CANDIDATES = 40

# $3: law numbers to search in, or NULL for every indexed law.
_FTS_SQL = """
SELECT id FROM statute_articles
WHERE tsv @@ any_terms('turkish', $1) AND ($3::text[] IS NULL OR law_number = ANY($3))
ORDER BY ts_rank_cd(tsv, any_terms('turkish', $1)) DESC
LIMIT $2
"""
_VECTOR_SQL = """
SELECT id FROM statute_articles WHERE ($3::text[] IS NULL OR law_number = ANY($3))
ORDER BY embedding <=> $1 LIMIT $2
"""
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
    fts = [r["id"] for r in await conn.fetch(_FTS_SQL, query, CANDIDATES, laws)]
    vec = [r["id"] for r in await conn.fetch(_VECTOR_SQL, embed_query(query), CANDIDATES, laws)]
    scores = fuse([fts, vec])
    rows = {r["id"]: r for r in await conn.fetch(_ROWS_SQL, list(scores))}
    hits = [_hit(rows[i], s) for i, s in sorted(scores.items(), key=lambda kv: -kv[1])]
    return hits[:limit]


async def indexed_laws(conn: asyncpg.Connection) -> dict[str, str]:
    """Law number -> official title, for every law in the index."""
    rows = await conn.fetch("SELECT DISTINCT law_number, law_title FROM statute_articles")
    return {r["law_number"]: r["law_title"] for r in rows}


def law_number_of(law: str, laws: dict[str, str]) -> str | None:
    """Indexed law number for a number, "<number> <numbered-law word> ...", a customary
    abbreviation or a
    (partial) official name. `laws`: law number -> title, as from `indexed_laws`. Only current
    laws are indexed, so a name matches the law that carries it today."""
    law = law.strip()
    # An indexed law number anywhere in the text: "6100", "6098 <numbered> ...", or the form
    # the planner copies from its candidate list, "Law 6098 (<TITLE>)".
    numbers = re.findall(r"\b(\d{3,5})\b", law)
    for number in numbers:
        if number in laws:
            return number
    if numbers and re.match(r"^\W*\d", law):
        return None
    abbreviations = {tr_fold(k).rstrip("."): v for k, v in law_abbreviations().items()}
    found = abbreviations.get(tr_fold(law).rstrip("."))
    if found:
        return found if found in laws else None
    for kind in ("exact", "partial"):
        for law_number, title in laws.items():
            if name_match(law, title) == kind:
                return law_number
    return None


async def find_law(conn: asyncpg.Connection, law: str) -> str | None:
    return law_number_of(law, await indexed_laws(conn))


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


async def neighbours(conn: asyncpg.Connection, law: str, label: str, span: int = 2
                     ) -> list[StatuteHit]:
    """Main articles within `span` of the given one in the same law (codes keep related
    rules next to each other), nearest first."""
    number = await find_law(conn, law)
    ref = parse_article_label(str(label))
    if number is None or ref is None or ref[0] != "main":
        return []
    rows = await conn.fetch(
        _ROWS_SQL.replace("WHERE id = ANY($1::int[])",
                          "WHERE law_number = $1 AND kind = 'main' AND label = ANY($2::text[])"),
        number, [str(ref[1] + d) for d in range(-span, span + 1) if d])
    return sorted((_hit(r) for r in rows), key=lambda h: abs(int(h.label) - ref[1]))
