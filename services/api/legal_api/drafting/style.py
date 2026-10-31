"""Measured style of a petition: what code can read from the text without a model.

These features are what lawyers differ on (length, sentence length, register, structure), so
they are compared between a draft and the lawyer's own petitions, and averaged into the
lawyer's profile.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from legal_api.grounding.normalize import tr_fold
from legal_api.locale import style_terms

WORDS_PER_PAGE = 450        # a typed A4 page of petition text
_WORD = re.compile(r"\w+", re.UNICODE)
# An upper-case label ending in a colon, optionally numbered ("II. EXPLANATIONS :", "A) SUBJECT:").
_HEADING = re.compile(r"^\s*(?:(?:[IVX]+|\d+|[A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc])[.)-]\s*)?"
                      r"([A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc][A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc .,/()]{2,40}?)\s*:", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*(\d+)[.)-]\s+", re.MULTILINE)


@dataclass
class Style:
    words: int = 0
    pages: float = 0.0
    words_per_sentence: float = 0.0
    paragraphs: int = 0
    formal_per_1000: float = 0.0   # formal or archaic words per 1,000 words: the register
    headings: list[str] = field(default_factory=list)
    numbered_paragraphs: int = 0
    closing: str | None = None
    opening: str | None = None
    decision_citations: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    ends = re.escape(style_terms()["sentence_end"])
    parts = re.split(rf"(?<=[{ends}])\s+", " ".join(text.split()))
    return [p for p in parts if _WORD.search(p)]


def _found(formulas: list[str], folded: str) -> str | None:
    hits = [(folded.find(tr_fold(f)), f) for f in formulas if tr_fold(f) in folded]
    return min(hits)[1] if hits else None


def without_markup(text: str) -> str:
    """Markdown emphasis and heading marks removed, as a lawyer's Word file has none."""
    text = re.sub(r"\*\*|__", "", text)
    return re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)


def petition_part(text: str) -> str:
    """The petition itself: a draft has a one-line note before it and a checklist after it,
    each set off by a line of three dashes."""
    parts = re.split(r"^\s*---\s*$", text, flags=re.MULTILINE)
    return max(parts, key=len) if len(parts) >= 3 else text


def petition_span(text: str) -> tuple[int, int]:
    """Where the petition itself starts and ends in a draft (the whole text when it has no
    note and checklist set off by dashes)."""
    seps = list(re.finditer(r"^\s*---\s*$", text, flags=re.MULTILINE))
    if len(seps) < 2:
        return 0, len(text)
    bounds = [0, *(x for m in seps for x in (m.start(), m.end())), len(text)]
    spans = list(zip(bounds[::2], bounds[1::2], strict=True))
    return max(spans, key=lambda s: s[1] - s[0])


def around_petition(text: str) -> str:
    """A draft without the petition: the note before it and the checklist after it, which
    is what the chat shows next to the file."""
    parts = re.split(r"^\s*---\s*$", text, flags=re.MULTILINE)
    if len(parts) < 3:
        return text
    body = max(parts, key=len)
    return "\n\n".join(p.strip() for p in parts if p is not body and p.strip())


def measure(text: str) -> Style:
    terms = style_terms()
    text = without_markup(text)
    words = _WORD.findall(text)
    if not words:
        return Style()
    folded = tr_fold(text)
    formal = {tr_fold(w) for w in terms["formal_words"]}
    formal_count = sum(1 for w in words if tr_fold(w) in formal)
    sentences = _sentences(text)
    paragraphs = [p for p in re.split(r"\n\s*\n|\n(?=\s*\d+[.)-]\s)", text) if p.strip()]
    closing_part = folded[-max(400, len(folded) // 5):]
    return Style(
        words=len(words),
        pages=round(len(words) / WORDS_PER_PAGE, 1),
        words_per_sentence=round(len(words) / max(1, len(sentences)), 1),
        paragraphs=len(paragraphs),
        formal_per_1000=round(1000 * formal_count / len(words), 1),
        headings=list(dict.fromkeys(" ".join(h.split()).rstrip(" .") for h in
                                    _HEADING.findall(text))),
        numbered_paragraphs=len(_NUMBERED.findall(text)),
        closing=_found(terms["closing_formulas"], closing_part),
        opening=_found(terms["opening_formulas"], folded),
        decision_citations=len(re.findall(rf"\b{re.escape(terms['decision_marker'])}\b", text)),
    )
