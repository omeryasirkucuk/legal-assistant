"""Numbers stated in a text, written as digits or as Turkish number words.

Periods, amounts and ratios are what a lawyer acts on, so a sentence written over cited
sub-answers may only state numbers that appear in them. Statutes write numbers as separate
words or, in older texts, joined into one word (eighteen as "onsekiz", twenty-four as
"yirmidört"); both are read.
"""

from __future__ import annotations

import re
from functools import cache

from legal_api.grounding.normalize import tr_fold
from legal_api.locale import number_units, number_words

_TOKEN = re.compile(r"\d+/\d+|\d+(?:[.,]\d+)?|\w+")
# "dörtte bir" (one quarter): denominator word with the locative ending, then the numerator
# word with any ending ("dörtte birinden", "dörtte üçüne").
_LOCATIVE = ("te", "ta", "de", "da")
MAX_DENOMINATOR = 12
# The word for one stands alone too often as "a" to count, but inside a joined number
# ("onbir", eleven) it is unambiguous.
_ONE = "bir"


@cache
def _words() -> dict[str, int]:
    return {tr_fold(k): v for k, v in number_words().items()}


@cache
def _parts() -> dict[str, int]:
    return {**_words(), _ONE: 1}


def _split(token: str) -> list[int] | None:
    """Values of a joined number word ("onsekiz" -> [10, 8]); None if it is not one."""
    parts = _parts()
    if token == "":
        return []
    for size in range(len(token), 1, -1):
        head = token[:size]
        if head in parts:
            rest = _split(token[size:])
            if rest is not None:
                return [parts[head], *rest]
    return None


def _values(token: str) -> list[int] | None:
    if token in _words():
        return [_words()[token]]
    split = _split(token)
    return split if split and len(split) > 1 else None


class _Number:
    """Accumulates consecutive number words: ten + eight -> 18, two + hundred -> 200."""

    def __init__(self) -> None:
        self.total = 0
        self.current = 0
        self.started = False

    def add(self, value: int) -> None:
        self.started = True
        if value == 100:
            self.current = max(self.current, 1) * 100
        elif value == 1000:
            self.total += max(self.current, 1) * 1000
            self.current = 0
        else:
            self.current += value

    def flush(self, found: set[float]) -> None:
        if self.started:
            found.add(float(self.total + self.current))
        self.__init__()


def _denominator(token: str) -> int | None:
    for ending in _LOCATIVE:
        stem = token[:-len(ending)]
        if token.endswith(ending) and stem in _words() and 1 < _words()[stem] <= MAX_DENOMINATOR:
            return _words()[stem]
    return None


def _numerator(token: str) -> int | None:
    """A number word at the start of a token, whatever ending follows ("üçüne" -> 3)."""
    for size in range(len(token), 1, -1):
        if token[:size] in _parts() and _parts()[token[:size]] < MAX_DENOMINATOR:
            return _parts()[token[:size]]
    return None


def _digit_fraction(token: str) -> float | None:
    """"1/4" -> 0.25; other slashes (case numbers "2025/6036") are not fractions."""
    a, b = (int(x) for x in token.split("/"))
    return a / b if 0 < a < b <= MAX_DENOMINATOR else None


def numbers_in(text: str) -> set[float]:
    """Every number in `text`. Adjacent number words make one number (ten + five -> 15);
    fractions, in digits or words, count as their value (1/4 and "dörtte bir" -> 0.25)."""
    found: set[float] = set()
    number = _Number()
    tokens = _TOKEN.findall(tr_fold(text))
    skip = False
    for i, token in enumerate(tokens):
        if skip:
            skip = False
            continue
        if "/" in token:
            number.flush(found)
            fraction = _digit_fraction(token)
            if fraction is not None:
                found.add(fraction)
            else:
                found.update(float(x) for x in token.split("/"))
            continue
        denominator = _denominator(token)
        numerator = _numerator(tokens[i + 1]) if denominator and i + 1 < len(tokens) else None
        if denominator and numerator and numerator < denominator:
            number.flush(found)
            found.add(numerator / denominator)
            skip = True
            continue
        if token[0].isdigit():
            number.flush(found)
            found.add(float(token.replace(",", ".")))
            continue
        values = _values(token)
        if values is None:
            number.flush(found)
            continue
        for value in values:
            number.add(value)
    number.flush(found)
    return found


def unsupported_numbers(claim: str, sources: list[str]) -> set[float]:
    """Numbers in `claim` that none of `sources` states."""
    stated: set[float] = set()
    for source in sources:
        stated |= numbers_in(source)
    return numbers_in(claim) - stated


def digits_for_quantities(text: str) -> str:
    """Number words written before a unit become digits ("Beş gün" -> "5 gün"), so a short
    answer shows quantities the same way throughout. Other words are left alone."""
    units = "|".join(re.escape(u) for u in sorted(number_units(), key=len, reverse=True))
    pattern = re.compile(rf"\b((?:\w+\s+){{0,3}}?\w+)(\s+)(?=(?:{units})\w*\b)", re.IGNORECASE)

    def replace(m: re.Match) -> str:
        words = m.group(1).split()
        # The longest tail of words that is wholly a number ("on beş", "onsekiz").
        for start in range(len(words)):
            tail = words[start:]
            values = [_values(tr_fold(w)) for w in tail]
            if all(values):
                number = _Number()
                for vs in values:
                    for v in vs:
                        number.add(v)
                found: set[float] = set()
                number.flush(found)
                head = " ".join(words[:start])
                return f"{head} {int(found.pop())}".lstrip() + m.group(2)
        return m.group(0)

    return pattern.sub(replace, text)
