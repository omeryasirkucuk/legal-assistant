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
from dataclasses import dataclass
from functools import cache

from legal_api import decisions, llm
from legal_api.agent.atoms import Segment, openai_segments_from
from legal_api.agent.power import POWERS, Power
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.grounding.numbers import digits_for_quantities, numbers_in, unsupported_numbers
from legal_api.locale import reference_terms
from legal_api.prompts import prompt

MAX_DOCUMENT_CHARS = 8000
CITE_AGAIN = ("<note>The previous attempt cited no document. Cite the documents for every legal "
              "statement using the citation feature.</note>")
# Includes the model's thinking; 4,000 cut a consultation answer off mid-section.
MAX_TOKENS = 8000
# Correct sentences scored about 0.9, a period applied to the wrong case 0.67, plain errors
# below 0.05 (probe on obligations law art. 315, 2026-10-30). At 0.8 correct sentences in long
# paragraphs (decision quotes, relations between provisions) were flagged too, so only clear
# contradictions are flagged; wrong-case errors are not caught by this check.
SUPPORTED = 0.5
CHECK_SOURCE_CHARS = 6000
MAX_PARAGRAPH_CHARS = 2000
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
        return openai_segments_from(final.content, sources)
    out = []
    for block in final.content:
        if block.type != "text":
            continue
        cites = block.citations or []
        keys = tuple(dict.fromkeys(sources[c.document_index].evidence.key for c in cites
                                   if c.document_index < len(sources)))
        out.append(Segment(block.text, keys, tuple(c.cited_text for c in cites)))
    return out


# Zero-width characters in statute texts were copied into answers, sometimes as the literal
# escape "\u200b"; both forms are removed.
_INVISIBLE = re.compile(r"\\u200[bcd]|\\ufeff|[\u200b\u200c\u200d\ufeff]")


# A document key written into the prose ("the closest are E10 and E12"); the lawyer cannot
# read it, so it becomes a citation marker (shown as a chip that opens the source).
_BARE_KEY = re.compile(r"(?<!\[\[)\b(E\d+)\b(?!\]\])")


def clean(text: str, keys: set[str] | None = None) -> str:
    text = _INVISIBLE.sub("", text)
    if keys:
        text = _BARE_KEY.sub(lambda m: f"[[{m.group(1)}]]" if m.group(1) in keys else m.group(0),
                             text)
    return text


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
    source, they are not quantities to check ("m. 29/1", "6098 sayılı", "E. 2019/1483")."""
    for pattern in _citation_patterns():
        text = pattern.sub(" ", text)
    return _MARKDOWN.sub(" ", text)


def _referenced_sources(segment: Segment, sources: list[Source]) -> list[Source]:
    """The sources a sentence cites, and those whose article it names in its text."""
    named = set(re.findall(r"\d+(?:/\w+)?", segment.text))
    return [s for s in sources if s.evidence.key in segment.keys
            or (getattr(s.evidence, "article_number", None)
                and s.evidence.article_number in named)]


async def check(segments: list[Segment], sources: list[Source], message: str,
                usage: llm.Usage) -> list[dict]:
    """Sentences stating quantities are checked: every number must appear in a source (first
    the ones the sentence cites or names, else any), and a sentence that cites or names its
    sources must be judged supported by them (a period applied to the wrong case passes a
    number check but not this one)."""
    titles = [s.evidence.citation for s in sources] + [message]
    to_judge: list[tuple[Segment, list[Source]]] = []
    flagged: list[dict] = []
    for seg in segments:
        body = without_citations(seg.text)
        if not numbers_in(body):
            # A citation with no quote matched to its source (a writer without document
            # citations) is judged against its sources like a sentence with numbers.
            if seg.keys and not seg.quotes:
                to_judge.append((seg, _referenced_sources(seg, sources)))
            continue
        relied = _referenced_sources(seg, sources)
        missing = unsupported_numbers(body, [*seg.quotes, *(s.document for s in relied),
                                             *titles])
        if missing:
            # Not in the sources the sentence relies on: a number no source states at all is
            # flagged; one stated elsewhere is judged against every source below.
            missing = unsupported_numbers(body, [*(s.document for s in sources), *titles])
            if missing:
                flagged.append(_flag(seg, ", ".join(f"{n:g}" for n in sorted(missing))))
                continue
            relied = []
        if relied:
            to_judge.append((seg, relied))
    if to_judge and decisions.enabled():
        context = _paragraphs(segments)
        # Every source, not only the ones the sentence names: a correct sentence may rest on a
        # source it does not name; a wrong one is still contradicted by the one it does.
        everything = "\n\n".join(f"{s.evidence.citation}:\n{s.document[:CHECK_SOURCE_CHARS]}"
                                   for s in sources)
        async with decisions.client() as client:
            verdicts = await asyncio.gather(*(
                decisions.yes_probabilities(
                    client, {"sentence": seg.text.strip(), "paragraph": context[id(seg)],
                             "sources": everything},
                    {"supported": SUPPORT_CHECK}, usage, "check")
                for seg, _ in to_judge))
        for (seg, _), v in zip(to_judge, verdicts, strict=True):
            if v["supported"] is not None and v["supported"] < SUPPORTED:
                flagged.append(_flag(seg, ""))
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


def _flag(seg: Segment, note: str) -> dict:
    return {"sentence": seg.text.strip(), "keys": list(seg.keys), "verdict": "not_supported",
            "note": note}


async def write(message: str, u: Understanding, sources: list[Source], usage: llm.Usage,
                instruction: str | None = None, previous: str | None = None,
                max_tokens: int = MAX_TOKENS, power: Power = POWERS["balanced"],
                context: list[dict] | None = None) -> AsyncIterator[str | Written]:
    """`context`: content blocks the lawyer attached (their documents' text, images), read
    as the case's material but not cited as legal sources."""
    """Yields text deltas while writing, then the Written answer."""
    system = prompt("write")
    if llm.openai_for(power.write_role):
        keys = ", ".join(s.evidence.key for s in sources)
        system += "\n\n" + prompt("quote_citations").replace("{keys}", keys)
    content = [*_documents(sources), *(context or []),
               {"type": "text", "text": _request(message, u, instruction, previous)}]
    final = None
    for attempt in range(2):
        async for item in llm.stream(power.write_role, usage, "write", max_tokens=max_tokens,
                                     system=system,
                                     output_config={"effort": power.write_effort},
                                     messages=[{"role": "user", "content": content}]):
            if isinstance(item, str):
                if attempt == 0:
                    yield item
            else:
                final = item
        segments = _segments(final, sources, power.write_role) if final else []
        # An answer that cites nothing cannot be checked or followed to its sources (one came
        # back as a single uncited block); it is written once more.
        if not sources or any(s.keys for s in segments) or llm.openai_for(power.write_role):
            break
        content[-1] = {"type": "text", "text": _request(message, u, instruction, previous)
                       + "\n" + CITE_AGAIN}
    flagged = await check(segments, sources, message, usage)
    if final is not None and final.stop_reason == "max_tokens":
        flagged.append({"sentence": "", "keys": [], "verdict": "not_supported",
                        "note": "answer cut off at the length limit"})
    # Quantities as digits throughout; checked above on the text as written.
    keys = {s.evidence.key for s in sources}
    segments = [Segment(digits_for_quantities(clean(s.text, keys)), s.keys, s.quotes)
                for s in segments]
    yield Written(segments, assemble(segments), flagged)
