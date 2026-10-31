"""Severance and notice pay, computed in code from the figures the lawyer gives.

- Length of service runs from the first day to the last; it is counted in whole years,
  months and days.
- Severance pay: thirty days' pay for each full year, the rest pro rata; the monthly pay
  used is the gross pay with regular extras, capped at the ceiling in force on the last day
  (locales/tr/severance.json, each ceiling with its source). Under one year gives none.
- Notice pay: two, four, six or eight weeks of pay by length of service (under 6, 18, 36
  months, or longer), a day's pay being the monthly pay over thirty.
- Stamp duty is shown deducted from severance pay; notice pay is shown gross, its income
  tax depending on the year's earlier pay.
Whether the ending of the contract gives a right to either is for the answer to argue from
the statutes; the calculation only says what the amounts are if it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

from legal_api.locale import severance_data

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Service:
    years: int
    months: int
    days: int

    @property
    def total_months(self) -> int:
        return self.years * 12 + self.months


@dataclass
class Severance:
    start: date
    end: date
    service: Service
    monthly: Decimal                 # gross pay with regular extras, as given
    ceiling: Decimal | None          # in force on the last day; None if not listed
    base: Decimal                    # monthly pay used, after the ceiling
    severance: Decimal
    stamp_duty: Decimal
    notice_weeks: int
    notice: Decimal
    warnings: list[str] = field(default_factory=list)   # codes


def service_length(start: date, end: date) -> Service:
    """Whole calendar years, months and days from the first day to the last, both counted
    (1 March to 31 August is six months): measured up to the day after the last."""
    stop = end + timedelta(days=1)
    years, months = stop.year - start.year, stop.month - start.month
    days = stop.day - start.day
    if days < 0:
        months -= 1
        prev_month_end = date(stop.year, stop.month, 1) - timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        years, months = years - 1, months + 12
    return Service(years, months, days)


@cache
def _data() -> dict:
    return severance_data()


def ceiling_on(day: date) -> Decimal | None:
    for c in _data()["ceilings"]:
        if date.fromisoformat(c["from"]) <= day <= date.fromisoformat(c["to"]):
            return Decimal(c["amount"])
    return None


def notice_weeks(service: Service) -> int:
    for rule in _data()["notice_weeks"]:
        if rule["under_months"] is None or service.total_months < rule["under_months"]:
            return rule["weeks"]
    return 0


def compute(start: date, end: date, monthly: Decimal) -> Severance:
    service = service_length(start, end)
    ceiling = ceiling_on(end)
    warnings = []
    if ceiling is None:
        warnings.append("ceiling_missing")
    base = min(monthly, ceiling) if ceiling is not None else monthly
    years = Decimal(service.years) + Decimal(service.months) / 12 + Decimal(service.days) / 365
    severance = (base * years).quantize(CENT, ROUND_HALF_UP) if service.years >= 1 else Decimal(0)
    if service.years < 1:
        warnings.append("under_one_year")
    stamp = (severance * Decimal(_data()["stamp_duty"])).quantize(CENT, ROUND_HALF_UP)
    weeks = notice_weeks(service)
    notice = (monthly / 30 * 7 * weeks).quantize(CENT, ROUND_HALF_UP)
    return Severance(start, end, service, monthly, ceiling, base, severance, stamp, weeks,
                     notice, warnings)
