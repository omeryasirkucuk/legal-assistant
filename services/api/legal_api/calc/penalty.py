"""Prison ranges read from penal provisions and the increases and decreases applied to them.

A model reads well but computes badly: asked how a weapon changes the penalty for injury, one
answer said the increase "was cut from the source", another multiplied by hand. Here the range
("from one year six months to three years' imprisonment") and the ratio ("increased by half")
are read from the article's own text (locales/tr/penalty.json holds the words) and applied in
code, both bounds, in the order of TCK art. 61 (a year is 12 months, a month 30 days,
fractions of a day dropped).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import cache

from legal_api.grounding.normalize import tr_fold
from legal_api.locale import penalty_terms

YEAR, MONTH = 360, 30


@dataclass(frozen=True)
class Range:
    low: int            # days
    high: int
    phrase: str         # the words it was read from
    fine: bool = False  # the provision also allows a judicial fine instead


@dataclass(frozen=True)
class Ratio:
    kind: str           # increase | decrease
    low: Fraction
    high: Fraction
    shape: str          # fixed | range | up_to
    phrase: str


@cache
def _vocab() -> dict:
    t = penalty_terms()
    alt = lambda words: "|".join(map(re.escape, sorted(words, key=len, reverse=True)))
    number = alt(t["numbers"])
    numeral = rf"(?:\d+|(?:{number})(?:\s*(?:{number}))*)"
    unit = alt(t["units"])
    duration = rf"(?:{numeral}\s+(?:{unit})\s+)*{numeral}\s+(?:{unit})"
    fraction = alt(t["fractions"])
    verbs = alt(t["increase"] + t["decrease"])
    return {
        "numbers": {tr_fold(k): v for k, v in t["numbers"].items()},
        "units": {tr_fold(k): v for k, v in t["units"].items()},
        "part": re.compile(rf"({numeral})\s+({unit})"),
        "range": re.compile(
            rf"(?<!\w)(?P<low>{duration})(?:{alt(t['from_suffixes'])})\s+(?P<high>{duration})"
            rf"(?:{alt(t['to_suffixes'])})\s+{re.escape(t['up_to'])}\s+{re.escape(t['imprisonment'])}"),
        "fine": tr_fold(t["fine"]),
        "between": re.compile(rf"(?<!\w)(?P<a>{fraction})\w*\s+(?P<b>{fraction})\w*\s+{re.escape(t['up_to'])}\w*"),
        "up_to": re.compile(rf"(?<!\w)(?P<a>{fraction})\w*\s+{re.escape(t['up_to'])}\w*"),
        "fixed": re.compile(rf"(?<!\w)(?P<a>{fraction})\w*(?=[\s,])"),
        "verb": re.compile(rf"(?<!\w)(?:{verbs})(?!\w)"),
        "fractions": {tr_fold(k): Fraction(*v) for k, v in t["fractions"].items()},
        "decrease": {tr_fold(v) for v in t["decrease"]},
        "item_only": re.compile(re.escape(tr_fold(t["item_only"])).replace(re.escape("{item}"), r"\w")),
    }


def _number(words: str) -> int | None:
    """The value of a number written in words (fourteen as two words or one) or digits."""
    if words.isdigit():
        return int(words)
    table, total, rest = _vocab()["numbers"], 0, words.replace(" ", "")
    while rest:
        match = next((w for w in sorted(table, key=len, reverse=True) if rest.startswith(w)), None)
        if match is None:
            return None
        total += table[match]
        rest = rest[len(match):]
    return total


def _days(duration: str) -> int | None:
    v = _vocab()
    total = 0
    for numeral, unit in v["part"].findall(duration):
        n = _number(numeral)
        if n is None:
            return None
        total += n * {"year": YEAR, "month": MONTH, "day": 1}[v["units"][unit]]
    return total or None


def paragraph(article_text: str, number: str | int | None) -> str:
    """One numbered paragraph ("(2) ...") of an article's text; the whole text without one."""
    if not number:
        return article_text
    marks = list(re.finditer(r"(?:^|\n|[-–])\s*\((\d+)\)\s", article_text))
    for i, m in enumerate(marks):
        if m.group(1) == str(number).strip():
            end = marks[i + 1].start() if i + 1 < len(marks) else len(article_text)
            return article_text[m.end():end].strip()
    return article_text


def read_range(text: str) -> Range | None:
    folded = tr_fold(text)
    m = _vocab()["range"].search(folded)
    if not m:
        return None
    low, high = _days(m.group("low")), _days(m.group("high"))
    if not low or not high or high < low:
        return None
    tail = folded[m.end():m.end() + 40]
    return Range(low, high, m.group(0), fine=_vocab()["fine"] in tail)


def _fraction(words: str) -> Fraction:
    table = _vocab()["fractions"]
    return table[next(k for k in sorted(table, key=len, reverse=True) if words.startswith(k))]


def read_ratio(text: str, item: str | None = None) -> Ratio | None:
    """The increase or decrease a provision sets; for a lettered item with a ratio of its own
    ("for item (f), twofold"), that one, else the general one."""
    v = _vocab()
    folded = tr_fold(text)
    own = tr_fold(penalty_terms()["item_only"].format(item=item)) if item else None
    if own and own in folded:
        folded = folded[folded.index(own) + len(own):]
    else:
        # Other items' own ratios are not this one's.
        folded = v["item_only"].split(folded)[0] + " " + " ".join(v["verb"].findall(folded)[:1])
    verb = v["verb"].search(folded)
    if not verb:
        return None
    kind = "decrease" if verb.group(0) in v["decrease"] else "increase"
    if m := v["between"].search(folded):
        a, b = _fraction(m.group("a")), _fraction(m.group("b"))
        return Ratio(kind, min(a, b), max(a, b), "range", m.group(0) + " " + verb.group(0))
    if m := v["up_to"].search(folded):
        return Ratio(kind, Fraction(0), _fraction(m.group("a")), "up_to",
                     m.group(0) + " " + verb.group(0))
    if m := v["fixed"].search(folded):
        a = _fraction(m.group("a"))
        return Ratio(kind, a, a, "fixed", folded[m.start():verb.end()][:160])
    return None


def apply(base: Range, ratios: list[Ratio]) -> tuple[int, int]:
    """Both bounds after each ratio in turn: an increase raises the lower bound by its least
    and the upper by its most; a decrease the other way round."""
    low, high = Fraction(base.low), Fraction(base.high)
    for r in ratios:
        if r.kind == "increase":
            low, high = low * (1 + r.low), high * (1 + r.high)
        else:
            low, high = low * (1 - r.high), high * (1 - r.low)
    return int(low), int(high)


def duration_text(days: int) -> str:
    w = penalty_terms()["words"]
    years, rest = divmod(days, YEAR)
    months, days = divmod(rest, MONTH)
    parts = [f"{n} {w[unit]}" for n, unit in ((years, "year"), (months, "month"), (days, "day")) if n]
    return " ".join(parts) or f"0 {w['day']}"
