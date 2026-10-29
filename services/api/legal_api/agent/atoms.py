"""Answer one sub-question from its own sources, with citations bound by the API.

The model receives the sources as citation-enabled documents. Every statement it bases on a
source comes back with the exact cited passage (guaranteed by the API to exist in that
document), so grounding is checked by construction instead of by a second model pass.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from legal_api import llm
from legal_api.agent.decompose import Atom
from legal_api.agent.sources import Source, SourceFinder
from legal_api.config import get_settings
from legal_api.prompts import prompt

NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class Segment:
    text: str
    keys: tuple[str, ...] = ()        # evidence keys this text is cited to
    quotes: tuple[str, ...] = ()      # the exact cited passages


@dataclass
class AtomAnswer:
    atom: Atom
    found: bool
    segments: list[Segment] = field(default_factory=list)
    source_keys: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments).strip()

    @property
    def grounded(self) -> bool:
        """A found answer must carry at least one citation."""
        return not self.found or any(s.keys for s in self.segments)


async def gather_sources(atom: Atom, finder: SourceFinder) -> list[Source]:
    named = await asyncio.gather(*(finder.article(law, label) for law, label in atom.statutes))
    searched = await finder.articles_for(atom.ask)
    decisions = await finder.decisions_for(atom.case_query) if atom.case_query else []
    unique: dict[str, Source] = {}
    for source in [*(s for s in named if s), *searched, *decisions]:
        unique.setdefault(source.evidence.key, source)
    return list(unique.values())


def _documents(sources: list[Source]) -> list[dict]:
    return [{"type": "document",
             "source": {"type": "text", "media_type": "text/plain", "data": s.document},
             "title": s.evidence.citation,
             "citations": {"enabled": True}} for s in sources]


def segments_from(content, sources: list[Source]) -> list[Segment]:
    segments = []
    for block in content:
        if block.type != "text":
            continue
        cites = block.citations or []
        keys = tuple(dict.fromkeys(sources[c.document_index].evidence.key for c in cites
                                   if c.document_index < len(sources)))
        segments.append(Segment(block.text, keys, tuple(c.cited_text for c in cites)))
    return segments


async def answer_atom(atom: Atom, finder: SourceFinder, usage: llm.Usage) -> AtomAnswer:
    sources = await gather_sources(atom, finder)
    keys = [s.evidence.key for s in sources]
    if not sources:
        return AtomAnswer(atom, False, source_keys=keys)
    response = await llm.create(
        "main", usage, "atom", max_tokens=3000, system=prompt("atom_answer"),
        output_config={"effort": get_settings().answer_effort},
        messages=[{"role": "user", "content": [*_documents(sources),
                                               {"type": "text", "text": atom.ask}]}])
    segments = segments_from(response.content, sources)
    text = "".join(s.text for s in segments).strip()
    if response.stop_reason == "refusal" or not text or text.startswith(NOT_FOUND):
        return AtomAnswer(atom, False, source_keys=keys)
    return AtomAnswer(atom, True, segments, keys)
