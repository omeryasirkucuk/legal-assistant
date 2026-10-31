"""Court fees for filing a civil case and whether its decision can be appealed.

Fees follow the current tariff (locales/tr/court_costs.json, revalued every January). The
appeal limits rise every year by the revaluation rate, and the limit of the year the case was
filed applies (HMK ek 1/2 since Law 7550), so each year's limit is kept, not only this one's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from legal_api.locale import court_costs

MEASURES = ("proportional", "fixed", "unknown")
COURTS = ("sulh", "asliye")


@dataclass(frozen=True)
class Fees:
    application: Decimal
    proportional: Decimal | None   # whole decision fee on the value, at least the minimum
    advance: Decimal | None        # the part due when filing
    fixed: Decimal | None


@dataclass(frozen=True)
class Appeal:
    year: int
    istinaf_limit: int
    temyiz_limit: int
    hearing_limit: int
    istinaf: bool
    temyiz: bool
    hearing: bool


def _money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), ROUND_HALF_UP)


def fees(value: Decimal | None, court: str, measure: str, bodily_harm: bool = False) -> Fees:
    f = court_costs()["fees"]
    application = Decimal(f["application"][court if court in COURTS else "asliye"])
    proportional = advance = fixed = None
    if measure in ("proportional", "unknown") and value:
        proportional = _money(max(value * Decimal(f["decision_rate_per_mille"]) / 1000,
                                  Decimal(f["decision_minimum"])))
        advance = _money(proportional / (20 if bodily_harm else 4))
    if measure in ("fixed", "unknown") or not value:
        fixed = Decimal(f["decision_fixed"])
    return Fees(application, proportional, advance, fixed)


def limit(kind: str, year: int) -> int | None:
    return court_costs()["limits"][kind].get(str(year))


def appeal(value: Decimal, filed: date) -> Appeal | None:
    """Whether a decision on `value` can go to the regional court and on to the Court of
    Cassation, by the limits of the year the case was filed."""
    year = filed.year
    lim = [limit(k, year) for k in ("istinaf", "temyiz", "hearing")]
    if None in lim:
        return None
    ist, tem, hea = lim
    return Appeal(year, ist, tem, hea, value > ist, value > tem, value > hea)


def chain(base: int, rates: list[Decimal], thousands_from: int, first_year: int) -> dict[int, int]:
    """The limits a base amount reaches with each year's revaluation: rounded down to 10 TL
    as practice did, to 1,000 TL from the year the law said so."""
    out, amount = {first_year: base}, Decimal(base)
    for i, rate in enumerate(rates):
        year = first_year + i + 1
        amount = Decimal(out[year - 1]) * (1 + rate / 100)
        step = 1000 if year >= thousands_from else 10
        out[year] = int(amount // step * step)
    return out
