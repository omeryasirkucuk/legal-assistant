"""Add the required contents of the petition and build the writer's brief."""

from __future__ import annotations

import asyncio

from legal_api.agent.research import Research
from legal_api.agent.sources import SourceFinder
from legal_api.agent.understand import Understanding
from legal_api.drafting.brief import StyleBook, brief
from legal_api.drafting.cases import case_kinds
from legal_api.drafting.types import petition_types

DRAFT_MAX_TOKENS = 16000     # a long petition plus the model's thinking
DRAFT_CONTENTS_BUDGET_S = 2


async def _required(finder: SourceFinder, found: Research, articles) -> list[str]:
    keys = []
    try:
        async with asyncio.timeout(DRAFT_CONTENTS_BUDGET_S):
            for law, label in articles:
                source = await finder.article(law, label)
                if source is not None:
                    keys.append(source.evidence.key)
                    if all(s.evidence.key != source.evidence.key for s in found.sources):
                        found.sources.append(source)
    except TimeoutError:
        pass
    return keys


async def drafting_instruction(finder: SourceFinder, found: Research, u: Understanding,
                               book: StyleBook) -> str:
    ptype = petition_types().get(u.petition_type)
    required = await _required(finder, found, ptype.articles) if ptype else []
    kind = case_kinds().get(u.case_kind)
    if kind and ptype and ptype.id not in kind.petition_types:
        kind = None
    found.trace["petition_type"] = u.petition_type
    found.trace["case_kind"] = kind.id if kind else None
    found.trace["requests"] = u.requests
    book.area = u.area
    book.case_kind = u.case_kind if u.case_kind in case_kinds() else None
    return brief(ptype, book, required, kind, u.requests)
