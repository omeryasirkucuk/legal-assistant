"""Ready a petition draft: add the articles that set the type's required contents and a
court decision for each ground of the case to the sources, and build the writer's brief."""

from __future__ import annotations

import asyncpg

from legal_api import llm
from legal_api.agent.power import POWERS, Power
from legal_api.agent.research import Research, screening_question
from legal_api.agent.sources import Source, SourceFinder
from legal_api.agent.understand import Understanding
from legal_api.drafting.brief import StyleBook, brief
from legal_api.drafting.cases import case_kinds
from legal_api.drafting.types import petition_types

DRAFT_MAX_TOKENS = 16000     # a long petition plus the model's thinking
# Grounds searched for a precedent of their own, by how much work the answer gets. A lawyer's
# petition supports each ground with a decision where it is argued; one search for the whole
# case gave a divorce petition no decision at all.
# A fast petition searches none (D50): the three levels differ in what the lawyer gets, not
# only in which model writes.
GROUNDS = {"fast": 0, "balanced": 4, "deep": 6}
PER_GROUND_LIVE = 3


async def _add(found: Research, source: Source) -> str:
    if all(s.evidence.key != source.evidence.key for s in found.sources):
        found.sources.append(source)
    return source.evidence.key


async def _required(finder: SourceFinder, found: Research, articles) -> list[str]:
    keys = []
    for law, label in articles:
        source = await finder.article(law, label)
        if source is not None:
            keys.append(await _add(found, source))
    return keys


async def _precedents(finder: SourceFinder, found: Research, question: str, u: Understanding,
                      usage: llm.Usage, power: Power) -> dict[str, list[Source]]:
    """A decision for each ground, judged as a precedent for that ground in this case."""
    out: dict[str, list[Source]] = {}
    for name, phrase in u.issues[:GROUNDS.get(power.name, GROUNDS["balanced"])]:
        ask = screening_question(f"{question}\n(Ground: {name})", u)
        sources = await finder.decisions_for(phrase, ask, usage, keep=1,
                                             live_limit=PER_GROUND_LIVE, precedents=True)
        for s in sources:
            await _add(found, s)
        if sources:
            out[name] = sources
    found.trace["ground_precedents"] = sum(len(k) for k in out.values())
    return out


async def drafting_instruction(db: asyncpg.Pool, finder: SourceFinder, found: Research,
                               question: str, u: Understanding, book: StyleBook,
                               usage: llm.Usage, power: Power = POWERS["balanced"]) -> str:
    ptype = petition_types().get(u.petition_type)
    required = await _required(finder, found, ptype.articles) if ptype else []
    kind = case_kinds().get(u.case_kind)
    if kind and ptype and ptype.id not in kind.petition_types:
        kind = None
    precedents = await _precedents(finder, found, question, u, usage, power)
    found.trace["petition_type"] = u.petition_type
    found.trace["case_kind"] = kind.id if kind else None
    found.trace["requests"] = u.requests
    book.area = u.area
    book.case_kind = u.case_kind if u.case_kind in case_kinds() else None
    return brief(ptype, book, required, kind, precedents, u.requests)
