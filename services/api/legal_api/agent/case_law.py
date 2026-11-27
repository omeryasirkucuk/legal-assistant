"""Retrieve and verify court decisions within a single research pass."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from itertools import zip_longest
from typing import Literal

import asyncpg

from legal_api import decisions, llm
from legal_api.corpus.chunking import chunk_text
from legal_api.corpus.ingest import cache_decisions
from legal_api.corpus.records import from_bedesten
from legal_api.grounding.normalize import tr_fold
from legal_api.retrieval.hybrid import search as search_local
from legal_api.sources.bedesten_decisions import BedestenDecisions
from legal_api.sources.gateway import SourceBlocked, SourceError
from legal_api.sources.types import Decision, DecisionRef

logger = logging.getLogger(__name__)

LOCAL_CANDIDATES = 6
LIVE_DECISIONS = 3
LIVE_BUDGET_S = 14
SUPPLEMENTAL_LIVE_BUDGET_S = 8
SEARCH_QUERY_S = 4
LOCAL_BUDGET_S = 3
CACHE_BUDGET_S = 1
DECISION_CHECK_S = 5
KEEP = 2
RELEVANT = 0.75
DIRECT = 0.85
Match = Literal["direct", "related"]

HOLDING = ("Does the passage include the deciding court's own legal reasoning or disposition "
           "on the legal route the lawyer seeks? Answer no for submissions, quoted lower court "
           "reasoning, an abstract rule alone, or a ruling on a different procedural issue.")
RELATED = ("Does the court's reasoning materially help answer the legal request, including "
           "helpful distinctions? Reject shared vocabulary or an abstract rule with no "
           "application to the request. Distinguish the deciding court from the parties.")
DIRECT_MATCH = ("Does the deciding court apply the requested legal route in a materially "
                "matching case? Require affirmative evidence from the case facts or holding "
                "for every required condition. Reject unknown facts, contradictions, excluded "
                "facts and cases decided on a different issue. Do not infer facts from an "
                "abstract statement of law, party submissions, or a quoted lower judgment.")


@dataclass(frozen=True)
class Passage:
    """Verbatim excerpts and the text and metadata behind their citation."""
    passage: str
    full_text: str
    local: dict | None = None
    live: Decision | None = None
    match: Match | None = None

    def identity(self) -> tuple:
        if self.live is not None:
            ref = self.live.ref
            chamber, case, decision, source = ref.chamber, ref.case_no, ref.decision_no, ref.source_id
        else:
            assert self.local is not None
            chamber, case, decision, source = (
                self.local[k] for k in ("chamber", "case_no", "decision_no", "source_id"))
        return (tr_fold(chamber), case, decision) if case and decision else (source,)


async def _local(conn: asyncpg.Connection, query: str, excerpt_query: str) -> list[Passage]:
    if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM corpus_decisions)"):
        return []
    hits = await search_local(conn, query, limit=LOCAL_CANDIDATES)
    texts = {r["id"]: r["text"] for r in await conn.fetch(
        "SELECT id, text FROM corpus_decisions WHERE id = ANY($1::text[])",
        [h.decision_id for h in hits])}
    return [Passage(_closest_passage(texts[h.decision_id], excerpt_query), texts[h.decision_id], local={
        "source_id": h.decision_id, "chamber": h.chamber, "case_no": h.case_no,
        "decision_no": h.decision_no, "decision_date": h.decision_date, "url": h.url})
        for h in hits if h.decision_id in texts]


def _terms(text: str) -> set[str]:
    return {word[:5] for word in re.findall(r"[^\W_]+", tr_fold(text))
            if len(word) >= 3 or word.isdigit()}


def _closest_passage(text: str, ask: str) -> str:
    """Keep relevant facts and the actual disposition, in source order."""
    chunks = [c.text for c in chunk_text(text)] or [text]
    terms = _terms(ask)
    overlaps = [terms & _terms(chunk) for chunk in chunks]
    selected = {len(chunks) - 1}
    covered = overlaps[-1].copy()
    while len(selected) < min(3, len(chunks)):
        remaining = (index for index in range(len(chunks)) if index not in selected)
        best = max(remaining, key=lambda index: (
            len(overlaps[index] - covered), len(overlaps[index]), index))
        selected.add(best)
        covered.update(overlaps[best])
    return "\n\n[…]\n\n".join(chunks[index] for index in sorted(selected))


async def _live(source: BedestenDecisions, query: str, ask: str,
                limit: int = LIVE_DECISIONS, *, supplemental: bool = False,
                alternative: str = "") -> list[Passage]:
    found: list[Decision] = []
    budget = SUPPLEMENTAL_LIVE_BUDGET_S if supplemental else LIVE_BUDGET_S
    try:
        async with asyncio.timeout(budget):
            batches: list[list[DecisionRef]] = []
            for phrase in dict.fromkeys((query, alternative)):
                if not phrase.strip():
                    continue
                try:
                    async with asyncio.timeout(SEARCH_QUERY_S):
                        _, refs = await source.search(phrase, size=limit)
                except SourceBlocked:
                    break
                except (SourceError, TimeoutError, ValueError):
                    continue
                batches.append(refs)
            unique = {ref.source_id: ref for group in zip_longest(*batches)
                      for ref in group if ref is not None}
            for ref in list(unique.values())[:limit]:
                try:
                    found.append(await source.fetch(ref))
                except SourceBlocked:
                    break
                except SourceError:
                    continue
    except TimeoutError:
        pass
    return [Passage(_closest_passage(d.text, ask), d.text, live=d) for d in found]


async def _screen(ask: str, passages: list[Passage], usage: llm.Usage, keep: int, *,
                  strict: bool, requirements: tuple[str, ...], include_related: bool
                  ) -> list[Passage]:
    if not passages:
        return []
    if not decisions.enabled():
        return [] if strict else passages[:keep]

    checks = {"related": RELATED}
    if strict:
        checks.update(holding=HOLDING, direct=DIRECT_MATCH)
        checks.update({f"condition_{i}": (
            f"Does the deciding court's own reasoning or accepted case facts establish this "
            f"condition for this case: {requirement}? Answer no if the passage leaves it "
            f"unknown, states only the general law, or merely quotes a party's submission.")
            for i, requirement in enumerate(requirements)})

    async with decisions.client() as client:
        async def assess(passage: Passage) -> dict:
            state = {"legal_request": ask, "required_conditions": requirements,
                     "decision_passages": passage.passage}
            try:
                async with asyncio.timeout(DECISION_CHECK_S):
                    return await decisions.yes_probabilities(
                        client, state, checks, usage, "case_law")
            except TimeoutError:
                return {}

        answers = await asyncio.gather(*(assess(p) for p in passages))

    scored = []
    for answer, passage in zip(answers, passages, strict=True):
        relevant = answer.get("related") or 0.0
        direct = min((answer.get(key) or 0.0 for key in checks if key != "related"), default=0.0)
        if direct >= DIRECT:
            scored.append((True, direct, replace(passage, match="direct")))
        elif include_related and relevant >= RELEVANT:
            scored.append((False, relevant, replace(passage, match="related")))
    scored.sort(key=lambda result: (result[0], result[1]), reverse=True)
    direct = [passage for is_direct, _, passage in scored if is_direct]
    related = [passage for is_direct, _, passage in scored if not is_direct]
    return [*direct, *(related[:2] if strict else related)][:keep]


async def case_passages(conn: asyncpg.Connection, source: BedestenDecisions, query: str,
                        ask: str, usage: llm.Usage, keep: int = KEEP,
                        live_limit: int = LIVE_DECISIONS, precedents: bool = False, *,
                        supplemental: bool = False, alternative: str = "",
                        requirements: tuple[str, ...] = (), include_related: bool = True
                        ) -> list[Passage]:
    """Check a shared candidate pool, prioritising decisions that satisfy every condition."""
    excerpt_query = " ".join((query, alternative, *requirements))

    async def local() -> list[Passage]:
        try:
            async with asyncio.timeout(LOCAL_BUDGET_S):
                return await _local(conn, f"{query} {alternative}".strip(), excerpt_query)
        except TimeoutError:
            return []

    archive, live = await asyncio.gather(
        local(), _live(source, query, excerpt_query, live_limit,
                       supplemental=supplemental, alternative=alternative))
    candidates = {p.identity(): p for p in [*archive, *live]}
    assessed = await _screen(ask, list(candidates.values()), usage, keep, strict=precedents,
                             requirements=requirements, include_related=include_related)
    if live:
        try:
            async with asyncio.timeout(CACHE_BUDGET_S):
                await cache_decisions(conn, [from_bedesten(p.live) for p in live if p.live])
        except (TimeoutError, asyncpg.PostgresError, ValueError):
            logger.warning("Public decision cache write skipped")
    return assessed
