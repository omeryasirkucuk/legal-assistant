"""Finding the sources for one sub-question, and registering them as evidence.

Every source is returned as (evidence, document text): the evidence holds the full text and
the citation shown to the user; the document text is what the model reads and cites from
(an article's text, or the relevant passage of a decision).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from legal_api import llm
from legal_api.agent.case_law import case_passages
from legal_api.grounding.evidence import Evidence, EvidenceLedger
from legal_api.retrieval.statutes import StatuteHit, get_article, neighbours, search_statutes
from legal_api.sources.bedesten_decisions import BedestenDecisions
from legal_api.sources.bedesten_statutes import BedestenStatutes
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.types import Article, StatuteRef

SEARCHED_ARTICLES = 4


@dataclass(frozen=True)
class Source:
    evidence: Evidence
    document: str


def article_document(hit: StatuteHit) -> str:
    """What a model reads for an article: where it sits in the law and its marginal title,
    then its text. The chapter decides the regime (the same "tenant's obligations" title
    exists for ordinary and for usufructuary leases)."""
    lines = []
    if hit.section:
        lines.append(f"Section: {hit.section}")
    if hit.heading:
        lines.append(f"Article title: {hit.heading}")
    return "\n".join([*lines, hit.text])


class SourceFinder:
    def __init__(self, ledger: EvidenceLedger, db: asyncpg.Pool, gateway: Gateway):
        self.ledger = ledger
        self._db = db
        self._live = BedestenStatutes(gateway)
        self._decisions = BedestenDecisions(gateway)

    def article_source(self, hit: StatuteHit) -> Source:
        statute = StatuteRef(hit.statute_id, hit.law_number, hit.law_title, "KANUN", None,
                             hit.url)
        evidence = self.ledger.add_article(Article(statute, f"idx:{hit.id}", hit.label,
                                                   hit.text, hit.fetched_at.isoformat(),
                                                   hit.url))
        return Source(evidence, article_document(hit))

    async def article(self, law: str, label: str) -> Source | None:
        """One named article: from the local index, else live from the official service."""
        async with self._db.acquire() as conn:
            hit = await get_article(conn, law, label)
        if hit is not None:
            return self.article_source(hit)
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

    async def neighbours_of(self, law: str, label: str) -> list[Source]:
        async with self._db.acquire() as conn:
            hits = await neighbours(conn, law, label)
        return [self.article_source(h) for h in hits]

    async def articles_for(self, question: str, limit: int = SEARCHED_ARTICLES) -> list[Source]:
        async with self._db.acquire() as conn:
            hits = await search_statutes(conn, question, limit=limit)
        return [self.article_source(h) for h in hits]

    async def decisions_for(self, query: str, ask: str, usage: llm.Usage, keep: int = 2,
                            live_limit: int = 4, precedents: bool = False) -> list[Source]:
        """Decision passages that answer `ask`, from the local archive and live search."""
        async with self._db.acquire() as conn:
            passages = await case_passages(conn, self._decisions, query, ask, usage, keep,
                                           live_limit, precedents)
        sources = []
        for p in passages:
            if p.live is not None:
                evidence = self.ledger.add_decision_ref(p.live.ref, p.full_text)
            else:
                evidence = self.ledger.add_decision(**p.local, text=p.full_text)
            sources.append(Source(evidence, p.passage))
        return sources
