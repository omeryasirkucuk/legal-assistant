"""Answer one sub-question from its own sources, with citations bound by the API.

The model receives the sources as citation-enabled documents. Every statement it bases on a
source comes back with the exact cited passage (guaranteed by the API to exist in that
document), so grounding is checked by construction instead of by a second model pass.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from legal_api import llm
from legal_api.agent.decompose import Atom
from legal_api.agent.queries import case_query
from legal_api.agent.sources import Source, SourceFinder
from legal_api.config import get_settings
from legal_api.grounding.normalize import contains_quote
from legal_api.prompts import prompt

NOT_FOUND = "NOT_FOUND"
MAX_RETRY_SOURCES = 8


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


async def gather_sources(atom: Atom, finder: SourceFinder, usage: llm.Usage) -> list[Source]:
    """The articles the plan names; a statute search only when none of them could be found.
    Searched articles next to named ones let a sub-question about one regime be answered from
    another regime's general rule (the general objection period instead of the special one)."""
    named = [s for s in await asyncio.gather(
        *(finder.article(law, label) for law, label in atom.statutes)) if s]
    searched = [] if named else await finder.articles_for(atom.ask)
    decisions = (await finder.decisions_for(atom.case_query, atom.ask, usage)
                 if atom.case_query else [])
    unique: dict[str, Source] = {}
    for source in [*named, *searched, *decisions]:
        unique.setdefault(source.evidence.key, source)
    return list(unique.values())


def _documents(sources: list[Source]) -> list[dict]:
    return [{"type": "document",
             "source": {"type": "text", "media_type": "text/plain", "data": s.document},
             "title": f"{s.evidence.key} | {s.evidence.citation}",
             "citations": {"enabled": True}} for s in sources]


def openai_segments_from(content, sources: list) -> list[Segment]:
    """OpenAI-compatible endpoints do not expose Anthropic's document citation objects.

    Require explicit evidence keys and exact quotes from the supplied sources, rejecting
    fabricated or unclickable citations.
    """
    text = "\n".join(block.text for block in content if block.type == "text").strip()
    matches = list(re.finditer(
        r'<quote\s+ref="(E\d+)">([\s\S]*?)</quote>\s*\[\[\1\]\]', text))
    cited_keys = re.findall(r"\[\[(E\d+)\]\]", text)
    allowed = {source.evidence.key if hasattr(source, "evidence") else source[0]
               for source in sources}
    documents = {
        (source.evidence.key if hasattr(source, "evidence") else source[0]):
            (source.document if hasattr(source, "evidence") else source[2])
        for source in sources
    }
    if not matches or len(matches) != len(cited_keys):
        return []
    keys, quotes = [], []
    for match in matches:
        key, quote = match.groups()
        if key not in allowed or not contains_quote(documents[key], quote):
            return []
        if key not in keys:
            keys.append(key)
        quotes.append(quote)
    if set(cited_keys) != set(keys):
        return []
    return [Segment(text, tuple(keys), tuple(quotes))]


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
    """Answer from the articles the plan names; if they do not answer it (the planner can
    name a wrong article from memory, often a neighbour of the right one), once more from the
    named articles' neighbours, a statute search on the sub-question and, when the planner
    asked for no case law, screened decision passages."""
    sources = await gather_sources(atom, finder, usage)
    answer = await _answer_from(atom, sources, usage)
    if answer.found or not atom.statutes:
        return answer
    named = {s.evidence.key for s in sources}
    nearby = [s for law, label in atom.statutes for s in await finder.neighbours_of(law, label)]
    retry_sources: dict[str, Source] = {}
    # Practice questions ("how is it proved") are answered by decisions, not articles.
    query = atom.case_query or await case_query(atom.ask, usage)
    decisions = (await finder.decisions_for(query, atom.ask, usage)
                 if query and not atom.case_query else [])
    for s in [*nearby, *await finder.articles_for(atom.ask)][:MAX_RETRY_SOURCES]:
        if s.evidence.key not in named:
            retry_sources.setdefault(s.evidence.key, s)
    for s in decisions:
        retry_sources.setdefault(s.evidence.key, s)
    if not retry_sources:
        return answer
    retry = await _answer_from(atom, list(retry_sources.values()), usage)
    return retry if retry.found else answer


async def _answer_from(atom: Atom, sources: list[Source], usage: llm.Usage) -> AtomAnswer:
    keys = [s.evidence.key for s in sources]
    if not sources:
        return AtomAnswer(atom, False, source_keys=keys)
    system = prompt("atom_answer")
    if llm.uses_openai_compatible():
        system += "\n\n" + prompt("quote_citations").replace("{keys}", ", ".join(keys))
    response = await llm.create(
        "main", usage, "atom", max_tokens=3000, system=system,
        output_config={"effort": get_settings().answer_effort},
        messages=[{"role": "user", "content": [*_documents(sources),
                                               {"type": "text", "text": atom.ask}]}])
    segments = segments_from(response.content, sources)
    text = "".join(s.text for s in segments).strip()
    if response.stop_reason == "refusal" or not text or text.startswith(NOT_FOUND):
        return AtomAnswer(atom, False, source_keys=keys)
    if llm.uses_openai_compatible():
        segments = openai_segments_from(response.content, sources)
        if not segments:
            return AtomAnswer(atom, False, source_keys=keys)
    return AtomAnswer(atom, True, segments, keys)
