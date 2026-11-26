"""A severance calculation written out step by step, as the source the answer cites."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from legal_api.calc.severance import Severance
from legal_api.locale import calculation_terms


def money(amount: Decimal) -> str:
    """Turkish format: 258.054,55 TL."""
    whole, cents = f"{amount:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents} TL"


def _day(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def render(r: Severance, *, assumed_end: bool = False) -> str:
    t = calculation_terms()["severance"]
    s = r.service
    lines = [t["title"]]
    if r.start is None:
        lines.append(t["months"].format(months=s.total_months))
        key = "assumed_end" if assumed_end else "end"
        lines.append(t[key].format(end=_day(r.end)))
    else:
        lines.append(t["service"].format(start=_day(r.start), end=_day(r.end), years=s.years,
                                         months=s.months, days=s.days))
    lines.append(t["monthly"].format(monthly=money(r.monthly)))
    if "under_one_year" in r.warnings:
        lines.append(t["under_one_year"])
    elif r.ceiling is None:
        lines.append(t["ceiling_missing"].format(end=_day(r.end)))
    else:
        lines.append(t["ceiling"].format(ceiling=money(r.ceiling), base=money(r.base)))
        lines.append(t["severance"].format(base=money(r.base), years=s.years,
                                           months=s.months, days=s.days,
                                           severance=money(r.severance)))
        lines.append(t["stamp"].format(stamp=money(r.stamp_duty),
                                       net=money(r.severance - r.stamp_duty)))
    lines.append(t["notice"].format(weeks=r.notice_weeks, monthly=money(r.monthly),
                                    days=r.notice_weeks * 7, notice=money(r.notice)))
    lines.append(t["condition"])
    return "\n".join(lines)


def ceiling_text(r: Severance) -> str:
    start, end = r.ceiling_period
    return calculation_terms()["severance"]["official_period"].format(
        start=_day(start), end=_day(end), ceiling=money(r.ceiling))
