"""Rules a petition must keep that a writer cannot be trusted to keep, applied in code after
every model-written draft or rewrite (never to the lawyer's own edits):

- Brackets name a missing datum ("[claim value]"). A writer with nowhere else to say a fact
  is missing wrote notes inside them ("[claim value; to be assessed separately for the
  property claim.]"); the note moves to the checklist and the bracket keeps its name.
- A petition does not talk about itself. Told to meet the statutes on a petition's contents,
  writers asserted they had ("it has been shown which fact each piece of evidence
  proves") even when told not to; such sentences are dropped (patterns in
  locales/tr/style.json, "self_reference").
- A petition that asks for an interim measure says so above its heading; writers asked for
  the measure and left the line out, so it is added when the requests ask for one.
"""

from __future__ import annotations

import re
from functools import cache

from legal_api.drafting.style import petition_span
from legal_api.grounding.normalize import tr_fold
from legal_api.locale import style_terms

MAX_LABEL_WORDS = 5
_BRACKET = re.compile(r"(?<!\[)\[([^\[\]\n]+)\](?!\])")
_SENTENCE = re.compile(r"[^.!?\n]*[.!?](?:\s*\[\[E\d+\]\])*|[^.!?\n]+$", re.MULTILINE)
_HEAD = re.compile(r"[;:,.(—–-]")


@cache
def _self_reference() -> list[re.Pattern]:
    return [re.compile(p) for p in style_terms().get("self_reference", [])]


def _label(note: str) -> tuple[str, str]:
    """A bracket's short name and what it said beyond that ("" when it was only a name)."""
    words = note.split()
    if len(words) <= MAX_LABEL_WORDS:
        return note.strip(), ""
    head = _HEAD.split(note, maxsplit=1)[0].strip()
    if not head or len(head.split()) > MAX_LABEL_WORDS:
        head = " ".join(words[:MAX_LABEL_WORDS])
    return head, note.strip()


def _talks_about_itself(sentence: str) -> bool:
    folded = tr_fold(sentence)
    return any(p.search(folded) for p in _self_reference())


def _interim_header(body: str) -> str:
    terms = style_terms()["interim_measure"]
    folded = tr_fold(body)
    heading = re.search(terms["requests_heading"], folded)
    requests = folded[heading.start():] if heading else ""
    if terms["request"] not in requests or terms["header_text"] in folded:
        return body
    lead = len(body) - len(body.lstrip())
    return f"{body[:lead]}{terms['header']}\n\n{body[lead:]}"


def tidy(text: str) -> str:
    start, end = petition_span(text)
    if (start, end) == (0, len(text)):
        return text
    body, notes = text[start:end], []

    def shorten(match: re.Match) -> str:
        label, note = _label(match.group(1))
        if note:
            notes.append(note)
        return f"[{label}]"

    body = _BRACKET.sub(shorten, body)
    body = _SENTENCE.sub(lambda m: "" if _talks_about_itself(m.group(0)) else m.group(0), body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = _interim_header(body)
    rest = text[end:].rstrip()
    if notes:
        rest += "\n" + "\n".join(f"- {n}" for n in dict.fromkeys(notes))
    return text[:start] + body + rest + "\n"
