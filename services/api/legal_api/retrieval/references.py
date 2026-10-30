"""Find the cross-references an article makes to other articles.

Statutes often state part of a rule by pointing elsewhere ("the notice in articles 260 and 288
of the Code of Obligations", "within the legal period"). An answer built only from the citing
article is then incomplete. This module only reads references out of the text; resolving them
to indexed articles is done by the caller.

A reference names its law by number ("6098 <numbered> ..."), by name (name words followed by
the law word), as the same law ("this law", or no law at all), and lists one or more article
labels. The Turkish vocabulary and alphabet are in locales/tr/references.json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from legal_api.grounding.normalize import tr_fold
from legal_api.locale import reference_terms

LOOKBACK_CHARS = 140


@dataclass(frozen=True)
class Reference:
    labels: tuple[str, ...]
    sentence: str                  # the sentence that makes the reference
    law_number: str | None = None  # referenced by law number
    law_name: str | None = None    # name words before the law word

    @property
    def same_law(self) -> bool:
        return self.law_number is None and self.law_name is None


def _alt(words: list[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


@cache
def _patterns() -> dict[str, re.Pattern]:
    t = reference_terms()
    label = rf"\d+(?:\s*/\s*[{t['lower_letters']}])?(?![\d/])"
    joiner = rf"\s*(?:,|\b(?:{_alt(t['joiners'])})\b)\s*"
    ordinal = rf"(?:\s*'?(?:{_alt(t['ordinals'])}))?"
    law = re.escape(t["law"])
    name_word = rf"(?:[{t['upper_letters']}][\w']*|{_alt(t['joiners'])})"
    return {
        "reference": re.compile(
            rf"(?<![\d/.])(?P<labels>{label}(?:{joiner}{label})*){ordinal}\s+"
            rf"{re.escape(t['article'])}\w*", re.IGNORECASE),
        "label": re.compile(label),
        "this_law": re.compile(rf"\b(?:{_alt(t['this'])})\s+{law}\w*\s*$"),
        "numbered": re.compile(
            rf"\b(\d{{3,5}})\s+{re.escape(t['numbered'])}\s+[^.;:]*?{law}\w*\s*$"),
        "named": re.compile(rf"((?:{name_word}\s+){{1,7}}){law}\w*\s*$"),
    }


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return " ".join(text[left + 1:right].split())


def _law_of(prefix: str) -> tuple[str | None, str | None]:
    """(law number, law name) named right before a reference; (None, None) for the same law."""
    p = _patterns()
    if p["this_law"].search(prefix):
        return None, None
    m = p["numbered"].search(prefix)
    if m:
        return m.group(1), None
    m = p["named"].search(prefix)
    if m:
        words = m.group(1).split()
        joiners = set(reference_terms()["joiners"])
        while words and words[0] in joiners:
            words.pop(0)
        if words:
            return None, " ".join(words)
    return None, None


def find_references(text: str) -> list[Reference]:
    p = _patterns()
    out: list[Reference] = []
    for m in p["reference"].finditer(text):
        labels = tuple(re.sub(r"\s+", "", x) for x in p["label"].findall(m.group("labels")))
        prefix = text[max(0, m.start() - LOOKBACK_CHARS):m.start()]
        number, name = _law_of(prefix)
        ref = Reference(labels, _sentence(text, m.start(), m.end()), number, name)
        if ref not in out:
            out.append(ref)
    return out


def law_core(title: str) -> tuple[str, ...]:
    """Folded name words of a law title without the law word (the title's words up to but
    excluding the word for "law")."""
    law = tr_fold(reference_terms()["law"])
    words = tr_fold(title).split()
    return tuple(w for w in words if not w.startswith(law))


def name_match(name: str, title: str) -> str | None:
    """"exact" if `name` is this law's name, "partial" if it is part of it (often the law
    this one replaced, whose name the current one extends), None otherwise."""
    ref, own = law_core(name), law_core(title)
    if not ref:
        return None
    if ref == own:
        return "exact"
    n = len(ref)
    if any(own[i:i + n] == ref for i in range(len(own) - n + 1)):
        return "partial"
    return None
