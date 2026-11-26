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
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from functools import cache
from itertools import batched

from legal_api import decisions, llm
from legal_api.agent.atoms import CitationStream, Segment, openai_segments_from, segments_from
from legal_api.agent.power import POWERS, Power
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.grounding.normalize import tr_fold
from legal_api.grounding.numbers import digits_for_quantities, numbers_in, unsupported_numbers
from legal_api.locale import reference_terms
from legal_api.prompts import prompt

MAX_DOCUMENT_CHARS = 8000
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
SUPPORT_BATCH_SIZE = 8
MIN_JUDGED_WORDS = 4    # words a piece needs to be judged on its own
SUPPORT_CHECK = ("Evaluate only this claim and its stated qualification, using its context "
                 "to resolve references. Treat an explicitly hypothetical fact as a premise, "
                 "never as legal authority. Accept a conditional application when the sources support the "
                 "legal rule and the condition is kept explicit. Check dates, quantities "
                 "and scope. Use case_facts only as reported facts, never as legal authority. Treat the "
                 "verified quotations as excerpts from the cited sources. Reject outcomes or rules the supplied sources do not support.")


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
    return _mask_citations(text)


def _mask_citations(text: str) -> str:
    for pattern in [*_citation_patterns(), _MARKDOWN]:
        text = pattern.sub(lambda match: " " * len(match[0]), text)
    return text


def _claim_bodies(segments: list[Segment]) -> Iterator[str]:
    # Match legal references before splitting at the writer's citation boundaries.
    masked = _mask_citations("".join(s.text for s in segments))
    offset = 0
    for segment in segments:
        end = offset + len(segment.text)
        yield masked[offset:end]
        offset = end


def _without_source_names(text: str, sources: list[Source]) -> str:
    words = tr_fold(text)
    for source in sources:
        label = tr_fold(without_citations(source.evidence.citation))
        # Punctuation in displayed source titles can differ from the ledger.
        parts = re.findall(r"\w+", label)
        if parts:
            pattern = r"\b" + r"[^\w]+".join(map(re.escape, parts)) + r"\b"
            words = re.sub(pattern, " ", words)
    return words


async def check(segments: list[Segment], sources: list[Source], message: str,
                usage: llm.Usage) -> list[dict]:
    """Check citation matches, quantities and, when enabled, support from cited sources."""
    to_judge: dict[tuple[str, ...], list[Segment]] = {}
    flagged: list[dict] = []
    for seg, body in zip(segments, _claim_bodies(segments), strict=True):
        if seg.unverified:
            flagged.append(_flag(seg, "", "citation_unmatched"))
        relied = [s for s in sources if s.evidence.key in seg.keys]
        judged = len(re.findall(r"[^\W\d_]{2,}", body)) >= MIN_JUDGED_WORDS
        if numbers_in(body):
            available = relied or sources
            missing = unsupported_numbers(body, [message, *seg.quotes,
                                                  *(s.document for s in available)])
            if missing:
                flagged.append(_flag(seg, ", ".join(f"{n:g}" for n in sorted(missing))))
                continue
        if relied and judged:
            remaining = set(re.findall(r"\w+", _without_source_names(body, relied)))
            if remaining <= set(reference_terms()["joiners"]):
                continue
            keys = tuple(s.evidence.key for s in relied)
            to_judge.setdefault(keys, []).append(seg)
    if to_judge and decisions.enabled():
        context = _paragraphs(segments)
        by_key = {s.evidence.key: s for s in sources}
        async with decisions.client() as client:
            batches = [(keys, batch) for keys, group in to_judge.items()
                       for batch in batched(group, SUPPORT_BATCH_SIZE)]
            verdicts = await asyncio.gather(*(
                _support_batch(client, batch, [by_key[k] for k in keys], context, message, usage)
                for keys, batch in batches))
        scores = {id(seg): score for (_, batch), verdict in zip(batches, verdicts, strict=True)
                  for seg, score in zip(batch, verdict, strict=True)}
        for seg in segments:
            score = scores.get(id(seg))
            if score is not None and score < SUPPORTED:
                flagged.append(_flag(seg, "", "support_low", "partial" if score >= PARTIAL
                                     else "not_supported"))
    return flagged


async def _support_batch(client, segments: tuple[Segment, ...], sources: list[Source],
                         context: dict[int, str], message: str, usage: llm.Usage) -> list[float | None]:
    claims = {f"claim_{i}": {"text": seg.text.strip(), "context": context[id(seg)],
                              "verified_quotations": [q[:2000] for q in seg.quotes]}
              for i, seg in enumerate(segments)}
    state = {"case_facts": message[:6000], "claims": claims, "sources": "\n\n".join(
        f"{s.evidence.citation}:\n{s.document[:CHECK_SOURCE_CHARS]}" for s in sources)}
    questions = {key: f"Evaluate only claims.{key}. {SUPPORT_CHECK}" for key in claims}
    verdict = await decisions.yes_probabilities(client, state, questions, usage, "check")
    return [verdict[key] for key in claims]


def _paragraphs(segments: list[Segment]) -> dict[int, str]:
    """Supply nearby text inside the paragraphs a cited segment actually touches."""
    out: dict[int, str] = {}
    full = "".join(seg.text for seg in segments)
    offset = 0
    margin = MAX_PARAGRAPH_CHARS // 4
    for seg in segments:
        end = offset + len(seg.text)
        claim = seg.text.strip()
        start_of_claim = end - len(seg.text.lstrip())
        end_of_claim = offset + len(seg.text.rstrip())
        before = full[max(0, start_of_claim - margin):start_of_claim].rsplit("\n\n", 1)[-1]
        after = full[end_of_claim:end_of_claim + margin].split("\n\n", 1)[0]
        remaining = MAX_PARAGRAPH_CHARS - len(before) - len(after)
        out[id(seg)] = (before + claim[:remaining] + after).strip()
        offset = end
    return out


def _flag(seg: Segment, note: str, reason: str | None = None,
          verdict: str = "not_supported") -> dict:
    return {"sentence": seg.text.strip(), "keys": list(seg.keys), "verdict": verdict,
            "note": note, **({"reason": reason} if reason else {})}


async def write(message: str, u: Understanding, sources: list[Source], usage: llm.Usage,
                instruction: str | None = None, previous: str | None = None,
                max_tokens: int = MAX_TOKENS, power: Power = POWERS["balanced"],
                context: list[dict] | None = None) -> AsyncIterator[str | Written]:
    """`context`: content blocks the lawyer attached (their documents' text, images), read
    as the case's material but not cited as legal sources."""
    """Yields text deltas while writing, then the Written answer."""
    system = prompt("write")
    compatible = llm.openai_for(power.write_role)
    if compatible:
        keys = ", ".join(s.evidence.key for s in sources)
        system += "\n\n" + prompt("quote_citations").replace("{keys}", keys)
    content = [*_documents(sources), *(context or []),
               {"type": "text", "text": _request(message, u, instruction, previous)}]
    final = None
    for attempt in range(2):
        citations = CitationStream()
        async for item in llm.stream(power.write_role, usage, "write", max_tokens=max_tokens,
                                     system=system,
                                     output_config={"effort": power.write_effort},
                                     messages=[{"role": "user", "content": content}]):
            if isinstance(item, str):
                if attempt == 0:
                    visible = citations.feed(item)
                    if visible:
                        yield visible
            else:
                final = item
        if attempt == 0 and (tail := citations.finish()):
            yield tail
        segments = _segments(final, sources, power.write_role) if final else []
        # An answer that cites nothing cannot be checked or followed to its sources (one came
        # back as a single uncited block); it is written once more.
        if not sources or any(s.keys for s in segments) or (final and final.stop_reason == "refusal"):
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
