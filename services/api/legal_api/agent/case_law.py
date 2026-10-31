"""Court-decision passages for one sub-question: local archive plus live search, screened.

The local archive is a small development subset, so for many questions it holds no decision
on point and its best matches are generic ("the law on evidence contracts is as follows").
Decisions are therefore also searched live (Bedesten, Court of Cassation), the passage of
each decision closest to the sub-question is taken, and every candidate passage is judged by
the decision model: does it state something that answers the sub-question? Only those are
given to the answering model, so a sub-answer is not left with generic passages to cite.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import asyncpg

from legal_api import decisions, llm
from legal_api.corpus.chunking import chunk_text
from legal_api.embeddings import embed_passages, embed_query
from legal_api.retrieval.hybrid import search as search_local
from legal_api.sources.bedesten_decisions import BedestenDecisions
from legal_api.sources.gateway import SourceError
from legal_api.sources.types import Decision

LOCAL_CANDIDATES = 4
LIVE_DECISIONS = 4
LIVE_BUDGET_S = 15
MIN_QUERY_WORDS = 2
KEEP = 2
RELEVANT = 0.7      # passages are judged more loosely than statute candidates
MAX_PASSAGE_CHARS = 6000

INSTRUCTIONS = ("A lawyer asked the sub-question. Answer yes only if the court-decision passage "
                "itself states a rule, test or finding that answers the sub-question (for "
                "example how something is proved, or when a provision applies). A passage that "
                "only quotes procedure, describes the parties' claims, or concerns another "
                "issue is no.")
# When the lawyer asks for decisions themselves, a decision on one of the case's issues is what
# is wanted; judged by the instruction above, such passages scored 0.55-0.64 against a request
# like "is there a precedent on this?" (0.9 and above with this one, procedure-only 0.15).
PRECEDENT = ("A lawyer asked for court decisions on the case described by the request and its "
             "legal characterisation. Answer yes if the court-decision passage decides or "
             "states the court's view on one of the legal issues of that case, so the lawyer "
             "could cite it as a precedent. A passage that only quotes procedure, only "
             "describes the parties' claims, or concerns a different legal issue is no.")


@dataclass(frozen=True)
class Passage:
    """A candidate passage and what is needed to register its decision as evidence."""
    passage: str
    full_text: str
    local: dict | None = None            # local archive row fields
    live: Decision | None = None         # live decision


async def _local(conn: asyncpg.Connection, query: str) -> list[Passage]:
    hits = await search_local(conn, query, limit=LOCAL_CANDIDATES)
    texts = {r["id"]: r["text"] for r in await conn.fetch(
        "SELECT id, text FROM corpus_decisions WHERE id = ANY($1::text[])",
        [h.decision_id for h in hits])}
    return [Passage(h.passage, texts[h.decision_id], local={
        "source_id": h.decision_id, "chamber": h.chamber, "case_no": h.case_no,
        "decision_no": h.decision_no, "decision_date": h.decision_date, "url": h.url})
        for h in hits]


def _closest_passage(text: str, ask: str) -> str:
    chunks = [c.text for c in chunk_text(text)] or [text]
    query = embed_query(ask)
    vectors = embed_passages(chunks)
    scores = [sum(a * b for a, b in zip(query, v, strict=True)) for v in vectors]
    return chunks[max(range(len(chunks)), key=scores.__getitem__)]


async def _search_relaxed(source: BedestenDecisions, query: str,
                          size: int = LIVE_DECISIONS) -> list:
    """The service matches every word; drop words from the end until something is found."""
    words = query.split()
    while words:
        _, refs = await source.search(" ".join(words), size=size)
        if refs or len(words) <= MIN_QUERY_WORDS:
            return refs
        words = words[:-1]
    return []


async def _live(source: BedestenDecisions, query: str, ask: str,
                limit: int = LIVE_DECISIONS) -> list[Passage]:
    """Live decisions within a time budget: requests to the service are queued process-wide
    at one per second and can each take up to the gateway timeout, so several answers
    searching at once could wait for minutes. Whatever arrived in time is used."""
    found: list[Decision] = []

    async def fetch_all() -> None:
        for ref in (await _search_relaxed(source, query, limit))[:limit]:
            found.append(await source.fetch(ref))

    try:
        await asyncio.wait_for(fetch_all(), LIVE_BUDGET_S)
    except (SourceError, TimeoutError):
        pass
    return [Passage(_closest_passage(d.text, ask), d.text, live=d) for d in found]


async def _screen(ask: str, passages: list[Passage], usage: llm.Usage,
                  keep: int = KEEP, instruction: str = INSTRUCTIONS) -> list[Passage]:
    if not decisions.enabled():
        return passages[:keep]
    async with decisions.client() as client:
        answers = await asyncio.gather(*(
            decisions.yes_probabilities(
                client, {"sub_question": ask, "decision_passage": p.passage[:MAX_PASSAGE_CHARS]},
                {"answers": instruction}, usage, "case_law")
            for p in passages))
    scored = [(a["answers"], p) for a, p in zip(answers, passages, strict=True)
              if a["answers"] is not None and a["answers"] >= RELEVANT]
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:keep]]


async def case_passages(conn: asyncpg.Connection, source: BedestenDecisions, query: str,
                        ask: str, usage: llm.Usage, keep: int = KEEP,
                        live_limit: int = LIVE_DECISIONS, precedents: bool = False
                        ) -> list[Passage]:
    """`precedents`: the lawyer asked for decisions themselves; more are read and kept, and
    they are judged as precedents for the case rather than as answers to a sub-question."""
    local = await _local(conn, query)
    live = await _live(source, query, ask, live_limit)
    seen, candidates = set(), []
    for p in [*live, *local]:
        key = (p.live.ref.case_no, p.live.ref.decision_no) if p.live else (
            p.local["case_no"], p.local["decision_no"])
        if key not in seen:
            seen.add(key)
            candidates.append(p)
    return await _screen(ask, candidates, usage, keep, PRECEDENT if precedents else INSTRUCTIONS)
