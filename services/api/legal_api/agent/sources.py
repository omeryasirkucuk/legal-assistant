"""Finding the sources for one sub-question, and registering them as evidence.

Every source is returned as (evidence, document text): the evidence holds the full text and
the citation shown to the user; the document text is what the model reads and cites from
(an article's text, or the relevant passage of a decision).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from legal_api.grounding.evidence import Evidence, EvidenceLedger
from legal_api.retrieval.hybrid import search as search_decisions
from legal_api.retrieval.statutes import StatuteHit, get_article, search_statutes
from legal_api.sources.bedesten_statutes import BedestenStatutes
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.types import Article, StatuteRef

SEARCHED_ARTICLES = 4
DECISION_PASSAGES = 2


@dataclass(frozen=True)
class Source:
    evidence: Evidence
    document: str


class SourceFinder:
    def __init__(self, ledger: EvidenceLedger, db: asyncpg.Pool, gateway: Gateway):
        self.ledger = ledger
        self._db = db
        self._live = BedestenStatutes(gateway)

    def _article(self, hit: StatuteHit) -> Source:
        statute = StatuteRef(hit.statute_id, hit.law_number, hit.law_title, "KANUN", None,
                             hit.url)
        evidence = self.ledger.add_article(Article(statute, f"idx:{hit.id}", hit.label,
                                                   hit.text, hit.fetched_at.isoformat(),
                                                   hit.url))
        return Source(evidence, hit.text)

    async def article(self, law: str, label: str) -> Source | None:
        """One named article: from the local index, else live from the official service."""
        async with self._db.acquire() as conn:
            hit = await get_article(conn, law, label)
        if hit is not None:
            return self._article(hit)
        try:
            if law.strip().isdigit():
                _, refs = await self._live.search(number=law.strip(), size=5)
                refs.sort(key=lambda r: r.kind != "KANUN")
            else:
                _, refs = await self._live.search(title=law, size=5)
            found = await self._live.article(refs[0], label) if refs else None
        except (SourceError, ValueError):
            return None
        return Source(self.ledger.add_article(found), found.text) if found else None

    async def articles_for(self, question: str, limit: int = SEARCHED_ARTICLES) -> list[Source]:
        async with self._db.acquire() as conn:
            hits = await search_statutes(conn, question, limit=limit)
        return [self._article(h) for h in hits]

    async def decisions_for(self, query: str, limit: int = DECISION_PASSAGES) -> list[Source]:
        async with self._db.acquire() as conn:
            hits = await search_decisions(conn, query, limit=limit)
            texts = {r["id"]: r["text"] for r in await conn.fetch(
                "SELECT id, text FROM corpus_decisions WHERE id = ANY($1::text[])",
                [h.decision_id for h in hits])}
        sources = []
        for hit in hits:
            evidence = self.ledger.add_decision(
                source_id=hit.decision_id, chamber=hit.chamber, case_no=hit.case_no,
                decision_no=hit.decision_no, decision_date=hit.decision_date, url=hit.url,
                text=texts[hit.decision_id])
            sources.append(Source(evidence, hit.passage))
        return sources
