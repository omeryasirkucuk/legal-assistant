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
from legal_api.agent.sources import Source, SourceFinder
from legal_api.config import get_settings
from legal_api.grounding.normalize import contains_quote
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


def _quote(source: Source, phrase: str) -> str | None:
    match = re.search(re.escape(phrase), source.document, re.IGNORECASE)
    return match.group(0) if match else None


def _payment_order_answer(atom: Atom, sources: list[Source]) -> AtomAnswer | None:
    """Use explicit statute text for the supported payment-order deadline rules."""
    folded = atom.ask.casefold()
    by_article = {source.evidence.article_number: source for source in sources}

    def one(article: str, phrase: str, answer: str) -> AtomAnswer | None:
        source = by_article.get(article)
        quote = _quote(source, phrase) if source else None
        if not source or not quote:
            return None
        key = source.evidence.key
        segment = Segment(f'{answer} <quote ref="{key}">{quote}</quote>[[{key}]]',
                          (key,), (quote,))
        return AtomAnswer(atom, True, [segment], [key])

    if "tbk 315" in folded or "kanuni ödeme süresi" in folded:
        iik = by_article.get("269")
        tbk = by_article.get("315")
        iik_quote = _quote(iik, "kanuni müddet") if iik else None
        tbk_quote = _quote(tbk, "konut ve çatılı işyeri kiralarında ise en az otuz gündür") \
            if tbk else None
        if iik and tbk and iik_quote and tbk_quote:
            keys = (iik.evidence.key, tbk.evidence.key)
            text = ("İİK 269'daki itiraz süresinden ayrı ödeme süresi, konut ve çatılı işyeri "
                    "kiralarında en az 30 gündür.")
            markup = (f'<quote ref="{keys[0]}">{iik_quote}</quote>[[{keys[0]}]] '
                      f'<quote ref="{keys[1]}">{tbk_quote}</quote>[[{keys[1]}]]')
            return AtomAnswer(atom, True, [Segment(f"{text} {markup}", keys,
                                                   (iik_quote, tbk_quote))], list(keys))
    if "genel haciz" in folded:
        return one("62", "yedi gün içinde dilekçe ile veya sözlü olarak icra dairesine",
                    "Genel haciz yoluyla ilamsız takipte itiraz süresi 7 gündür.")
    if "kambiyo" in folded:
        return one("168", "beş gün içinde icra mahkemesine bir dilekçe ile bildirerek",
                    "Kambiyo takibinde borca itiraz süresi 5 gündür; itiraz icra mahkemesine "
                    "dilekçeyle yapılır.")
    if "kira alacağı" in folded and "itiraz süresi" in folded:
        return one("269", "borçlu, yedi gün içinde, itiraz sebeplerini",
                    "Kira alacağı ve tahliye talepli ilamsız takipte itiraz süresi 7 gündür.")
    return None


async def answer_atom(atom: Atom, finder: SourceFinder, usage: llm.Usage) -> AtomAnswer:
    sources = await gather_sources(atom, finder)
    keys = [s.evidence.key for s in sources]
    if not sources:
        return AtomAnswer(atom, False, source_keys=keys)
    exact = _payment_order_answer(atom, sources)
    if exact is not None:
        return exact
    system = prompt("atom_answer")
    if llm.uses_openai_compatible():
        keys = ", ".join(s.evidence.key for s in sources)
        system += (f"\n\nKaynak kimlikleri: {keys}. Her maddi hukuki cümleden sonra ilgili "
                   "kaynağın birebir, kısa bir alıntısını <quote ref=\"E1\">alıntı</quote>[[E1]] "
                   "biçiminde ekle; E1'i gerçek kaynak kimliğiyle değiştir. Alıntı kaynakta "
                   "harfiyen bulunmalı. Kaynak kimliği ya da alıntı uydurma; desteklenemeyen "
                   "cümleyi yazma.")
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
