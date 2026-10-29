"""Hybrid search over the local decision corpus.

Full-text (Postgres `turkish` configuration) and vector (multilingual-e5) rankings are fused
with Reciprocal Rank Fusion, then collapsed to one hit per decision. Every hit carries the
decision's structured citation fields straight from the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import asyncpg

from legal_api.embeddings import embed_query

# Full-text matching uses any_terms() (see migration "any_terms"): a passage matches if it
# contains any of the query's terms and is ranked by how many and how close. Requiring all
# terms (websearch_to_tsquery) returns nothing for natural-language questions, because no
# passage contains "hangi", "kac", "midir" and the legal terms together.
RRF_K = 60
CANDIDATES = 50

_FTS_SQL = """
SELECT id FROM corpus_chunks
WHERE tsv @@ any_terms('turkish', $1)
ORDER BY ts_rank_cd(tsv, any_terms('turkish', $1)) DESC
LIMIT $2
"""
_VECTOR_SQL = "SELECT id FROM corpus_chunks ORDER BY embedding <=> $1 LIMIT $2"
_HITS_SQL = """
SELECT c.id AS chunk_id, c.start_char, c.text AS passage,
       d.id, d.chamber, d.case_no, d.decision_no, d.decision_date, d.url
FROM corpus_chunks c JOIN corpus_decisions d ON d.id = c.decision_id
WHERE c.id = ANY($1::bigint[])
"""


@dataclass(frozen=True)
class Hit:
    decision_id: str
    chamber: str
    case_no: str | None
    decision_no: str | None
    decision_date: date | None
    url: str
    passage: str
    passage_start: int
    score: float


def fuse(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return scores


async def search(conn: asyncpg.Connection, query: str, limit: int = 10) -> list[Hit]:
    fts_ids = [r["id"] for r in await conn.fetch(_FTS_SQL, query, CANDIDATES)]
    vector_ids = [r["id"] for r in await conn.fetch(_VECTOR_SQL, embed_query(query), CANDIDATES)]
    scores = fuse([fts_ids, vector_ids])
    rows = {r["chunk_id"]: r for r in await conn.fetch(_HITS_SQL, list(scores))}

    best: dict[str, Hit] = {}
    for chunk_id, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        row = rows[chunk_id]
        if row["id"] in best:
            continue
        best[row["id"]] = Hit(
            decision_id=row["id"], chamber=row["chamber"], case_no=row["case_no"],
            decision_no=row["decision_no"], decision_date=row["decision_date"], url=row["url"],
            passage=row["passage"], passage_start=row["start_char"], score=score,
        )
        if len(best) == limit:
            break
    return list(best.values())
