"""Direct decision search (the "Ara" mode): ranked results with citations, no LLM."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Query
from pgvector.asyncpg import register_vector

from legal_api.auth import CurrentUser
from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.grounding.evidence import decision_citation
from legal_api.retrieval.hybrid import search

router = APIRouter(prefix="/search", tags=["search"])

_pool: asyncpg.Pool | None = None


async def _db() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(asyncpg_dsn(), min_size=1, max_size=4,
                                          init=register_vector)
    return _pool


@router.get("/decisions")
async def decisions(user: CurrentUser, q: str = Query(min_length=2, max_length=500),
                    limit: int = Query(10, ge=1, le=30)) -> list[dict]:
    async with (await _db()).acquire() as conn:
        hits = await search(conn, q, limit)
    return [{
        "id": h.decision_id,
        "citation": decision_citation(h.chamber, h.case_no, h.decision_no, h.decision_date),
        "url": h.url,
        "passage": " ".join(h.passage.split()),
    } for h in hits]
