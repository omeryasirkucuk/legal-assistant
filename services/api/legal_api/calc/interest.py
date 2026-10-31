"""Simple interest on a principal from one day to another, period by period as the rate
changed (locales/tr/interest.json, each table with its source):
- "statutory": the statutory rate (3095 art. 1), for default interest in civil matters;
- "advance": the central bank's advance rate, for commercial matters (3095 art. 2/2).
Each stretch at one rate earns principal x rate x days / 365. Days before the first listed
rate, or after the date the tables were last checked, are flagged rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from typing import Literal

from legal_api.locale import interest_data

Kind = Literal["statutory", "advance"]
KINDS: tuple[Kind, ...] = ("statutory", "advance")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Stretch:
    start: date
    end: date            # inclusive
    days: int
    rate: Decimal        # yearly percent
    interest: Decimal


@dataclass
class Interest:
    kind: Kind
    principal: Decimal
    start: date
    end: date
    stretches: list[Stretch]
    total: Decimal
    warnings: list[str] = field(default_factory=list)   # codes


@cache
def _rates(kind: Kind) -> list[tuple[date, Decimal]]:
    return [(date.fromisoformat(r["from"]), Decimal(r["rate"])) for r in interest_data()[kind]]


@cache
def _known_until() -> date:
    return date.fromisoformat(interest_data()["known_until"])


def compute(principal: Decimal, start: date, end: date, kind: Kind) -> Interest:
    """Interest for the days after `start` up to and including `end`."""
    rates = _rates(kind)
    warnings = []
    first = start + timedelta(days=1)
    if first < rates[0][0]:
        warnings.append("before_rates")
        first = rates[0][0]
    if end > _known_until():
        warnings.append("after_known")
    stretches = []
    for i, (since, rate) in enumerate(rates):
        until = rates[i + 1][0] - timedelta(days=1) if i + 1 < len(rates) else end
        a, b = max(first, since), min(end, until)
        if a > b:
            continue
        days = (b - a).days + 1
        amount = (principal * rate / 100 * days / 365).quantize(CENT, ROUND_HALF_UP)
        stretches.append(Stretch(a, b, days, rate, amount))
    total = sum((s.interest for s in stretches), Decimal(0))
    return Interest(kind, principal, start, end, stretches, total, warnings)
