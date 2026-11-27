"""Write the answer as a whole, from all its sources, in the structure the task calls for.

The answer is written in one pass over every source, as citation-enabled documents, so it
can reason across them (apply the rule to the facts, compare routes, add the conditions a
lawyer must know) instead of joining one-sentence sub-answers. Grounding comes from the
Citations API; every sentence stating a quantity is checked against the sources it relies on
(numbers present, and the decision model judging it supported); failures are flagged, and
shown as unverified in the UI.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import date
from functools import cache

import anthropic
import httpx

from legal_api import decisions, llm
from legal_api.agent.atoms import CitationStream, Segment, openai_segments_from, segments_from
from legal_api.agent.power import POWERS, Power
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.clock import date_context, istanbul_date
from legal_api.grounding.numbers import digits_for_quantities, numbers_in, unsupported_numbers
from legal_api.locale import reference_terms
from legal_api.prompts import prompt

MAX_DOCUMENT_CHARS = 8000
CITATION_RETRY_S = 8
SUPPORT_CHECK_S = 5
CITE_AGAIN = ("<note>The previous attempt produced no verifiable citation. Follow the citation "
              "instructions for each sourced legal statement.</note>")
# Includes the model's thinking; 4,000 cut a consultation answer off mid-section.
MAX_TOKENS = 8000
# A probe scored a period applied to the wrong case at 0.67. Treat ambiguous scores as
# requiring review, since some accurate long paragraphs also scored below 0.8.
SUPPORTED = 0.8
PARTIAL = 0.5
CHECK_SOURCE_CHARS = 6000
MAX_PARAGRAPH_CHARS = 2000
MIN_JUDGED_WORDS = 4    # words a piece needs to be judged on its own
SUPPORT_CHECK = ("The sentence is part of the paragraph given. Answer yes only if what the "
                 "sentence states, read in its paragraph, is supported by the source texts, "
                 "including every number and the cases or persons it applies to. A number "
                 "applied to a different case than the source says is no.")


@dataclass
class Written:
    segments: list[Segment]
    text: str            # markdown with [[E#]] after each cited passage
    flagged: list[dict]  # sentences whose numbers no source supports


def _documents(sources: list[Source]) -> list[dict]:
    """Citation-enabled documents; a decision's title carries its date (citation), so the
    writer can tell a decision that applied an earlier law."""
    return [{"type": "document",
             "source": {"type": "text", "media_type": "text/plain",
                        "data": s.document[:MAX_DOCUMENT_CHARS]},
             "title": f"{s.evidence.key} | {s.evidence.citation}",
             "citations": {"enabled": True}} for s in sources]


def _request(message: str, u: Understanding, instruction: str | None,
             previous: str | None) -> str:
    parts = [f"<task>{u.task}</task>", f"<shape>{u.shape}</shape>",
             f"<message>{message}</message>"]
    if u.questions:
        parts.append("<questions>" + " | ".join(u.questions) + "</questions>")
    if u.characterisation:
        parts.append(f"<characterisation>{u.characterisation}</characterisation>")
    if u.missing_facts:
        parts.append("<missing_facts>" + " | ".join(u.missing_facts) + "</missing_facts>")
    if previous:
        parts.append(f"<previous_answer>{previous}</previous_answer>")
    if instruction:
        parts.append(f"<instruction>{instruction}</instruction>")
    return "\n".join(parts)


def _segments(final, sources: list[Source], role: llm.Role = "write") -> list[Segment]:
    if llm.openai_for(role):
        return openai_segments_from(final.content, sources, MAX_DOCUMENT_CHARS)
    return segments_from(final.content, sources)


# Zero-width characters in statute texts were copied into answers, sometimes as the literal
# escape "\u200b"; both forms are removed.
_INVISIBLE = re.compile(r"\\u200[bcd]|\\ufeff|[\u200b\u200c\u200d\ufeff]")


_RAW_MARKER = re.compile(r"[ \t]*\[\[E\d+\]\]")


def clean(text: str) -> str:
    return _RAW_MARKER.sub("", _INVISIBLE.sub("", text))


def assemble(segments: list[Segment]) -> str:
    """Segments joined, each cited one followed by its markers (before its trailing space)."""
    out = []
    for s in segments:
        body = s.text.rstrip()
        markers = "".join(f" [[{k}]]" for k in s.keys if f"[[{k}]]" not in s.text)
        out.append(body + markers + s.text[len(body):])
    return "".join(out).strip()


# List numbering and heading marks are layout, not quantities.
_MARKDOWN = re.compile(r"(?m)^[ \t]*(?:#+[ \t]*)?(?:\d+[.)][ \t]|[-*][ \t])?")


@cache
def _citation_patterns() -> list[re.Pattern]:
    return [re.compile(p) for p in reference_terms()["citation_patterns"]]


def without_citations(text: str) -> str:
    """Text with article, law, case and date references removed: their numbers identify a
    source, they are not quantities to check ("m. 29/1", "Law No. 6098", "E. 2019/1483")."""
    for pattern in _citation_patterns():
        text = pattern.sub(" ", text)
    return _MARKDOWN.sub(" ", text)


def _referenced_sources(segment: Segment, sources: list[Source]) -> list[Source]:
    return [s for s in sources if s.evidence.key in segment.keys]


async def check(segments: list[Segment], sources: list[Source], message: str,
                usage: llm.Usage) -> list[dict]:
    """Check citation matches, quantities and, when enabled, support from cited sources."""
    to_judge: list[tuple[Segment, list[Source]]] = []
    flagged: list[dict] = []
    for seg in segments:
        if seg.unverified:
            flagged.append(_flag(seg, "", "citation_unmatched"))
        body = without_citations(seg.text)
        # A piece cut off by citation marks ("315).**", "the fastest route.") cannot be judged
        # on its own; its numbers are still checked below.
        judged = len(re.findall(r"[^\W\d_]{2,}", body)) >= MIN_JUDGED_WORDS
        relied = _referenced_sources(seg, sources)
        if numbers_in(body):
            available = relied or sources
            missing = unsupported_numbers(body, [message, *seg.quotes,
                                                  *(s.document for s in available)])
            if missing:
                flagged.append(_flag(seg, ", ".join(f"{n:g}" for n in sorted(missing))))
                continue
        if relied and judged:
            to_judge.append((seg, relied))
    if to_judge and decisions.enabled():
        context = _paragraphs(segments)
        async with decisions.client() as client:
            async def support(seg: Segment, relied: list[Source]) -> float | None:
                state = {
                    "sentence": seg.text.strip(),
                    "paragraph": context[id(seg)],
                    "sources": "\n\n".join(
                        f"{s.evidence.citation}:\n{s.document[:CHECK_SOURCE_CHARS]}" for s in relied),
                }
                try:
                    async with asyncio.timeout(SUPPORT_CHECK_S):
                        verdict = await decisions.yes_probabilities(
                            client, state, {"supported": SUPPORT_CHECK}, usage, "check")
                    return verdict["supported"]
                except TimeoutError:
                    return None

            scores = await asyncio.gather(*(support(seg, relied) for seg, relied in to_judge))
        for (seg, _), score in zip(to_judge, scores, strict=True):
            if score is None:
                flagged.append(_flag(seg, "", "support_unavailable", "unverified"))
            elif score < SUPPORTED:
                flagged.append(_flag(seg, "", "support_low", "partial" if score >= PARTIAL
                                     else "not_supported"))
    return flagged


def _paragraphs(segments: list[Segment]) -> dict[int, str]:
    """The paragraph each segment belongs to: citations cut sentences into pieces, and a
    piece alone ("the period is three days.") cannot be judged."""
    out: dict[int, str] = {}
    paragraph: list[Segment] = []

    def close() -> None:
        text = "".join(s.text for s in paragraph).strip()
        for s in paragraph:
            out[id(s)] = text[:MAX_PARAGRAPH_CHARS]
        paragraph.clear()

    for seg in segments:
        parts = seg.text.split("\n\n")
        paragraph.append(seg)
        if len(parts) > 1:
            close()
    close()
    return out


def _flag(seg: Segment, note: str, reason: str | None = None,
          verdict: str = "not_supported") -> dict:
    return {"sentence": seg.text.strip(), "keys": list(seg.keys), "verdict": verdict,
            "note": note, **({"reason": reason} if reason else {})}


async def write(message: str, u: Understanding, sources: list[Source], usage: llm.Usage,
                instruction: str | None = None, previous: str | None = None,
                max_tokens: int = MAX_TOKENS, power: Power = POWERS["balanced"],
                context: list[dict] | None = None, *,
                today: date | None = None) -> AsyncIterator[str | Written]:
    """`context`: content blocks the lawyer attached (their documents' text, images), read
    as the case's material but not cited as legal sources."""
    """Yields text deltas while writing, then the Written answer."""
    system = f"{prompt('write')}\n\n{date_context(today or istanbul_date())}"
    compatible = llm.openai_for(power.write_role)
    if compatible:
        keys = ", ".join(s.evidence.key for s in sources)
        system += "\n\n" + prompt("quote_citations").replace("{keys}", keys)
    content = [*_documents(sources), *(context or []),
               {"type": "text", "text": _request(message, u, instruction, previous)}]
    final = None
    segments: list[Segment] = []
    for attempt in range(2):
        citations = CitationStream()
        response = None
        chunks = llm.stream(power.write_role, usage, "write", max_tokens=max_tokens,
                            system=system, output_config={"effort": power.write_effort},
                            messages=[{"role": "user", "content": content}])
        try:
            async with asyncio.timeout(CITATION_RETRY_S if attempt else None), aclosing(chunks):
                async for item in chunks:
                    if isinstance(item, str):
                        if attempt == 0 and (visible := citations.feed(item)):
                            yield visible
                    else:
                        response = item
        except (TimeoutError, anthropic.APIError, httpx.HTTPError):
            if not segments:
                raise
            break
        if attempt == 0 and (tail := citations.finish()):
            yield tail
        candidate = _segments(response, sources, power.write_role) if response else []
        has_citations = any(s.keys for s in candidate)
        if not segments or has_citations:
            final, segments = response, candidate
        if not sources or has_citations or (response and response.stop_reason == "refusal"):
            break
        content[-1] = {"type": "text", "text": _request(message, u, instruction, previous)
                       + "\n" + CITE_AGAIN}
    flagged = await check(segments, sources, message, usage)
    if (segments and not any(s.keys or s.unverified for s in segments)
            and (final is None or final.stop_reason != "refusal")):
        flagged.append(_flag(Segment(""), "", "citation_missing"))
    if final is not None and final.stop_reason == "max_tokens":
        flagged.append({"sentence": "", "keys": [], "verdict": "not_supported",
                        "note": "answer cut off at the length limit"})
    # Quantities as digits throughout; checked above on the text as written.
    segments = [Segment(digits_for_quantities(clean(s.text)), s.keys, s.quotes, s.unverified)
                for s in segments]
    yield Written(segments, assemble(segments), flagged)
