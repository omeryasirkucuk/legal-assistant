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


def render(r: Severance) -> str:
    t = calculation_terms()["severance"]
    s = r.service
    years = Decimal(s.years) + Decimal(s.months) / 12 + Decimal(s.days) / 365
    lines = [t["title"],
             t["service"].format(start=_day(r.start), end=_day(r.end), years=s.years,
                                 months=s.months, days=s.days),
             t["monthly"].format(monthly=money(r.monthly))]
    if r.ceiling is None:
        lines.append(t["ceiling_missing"].format(end=_day(r.end)))
    else:
        lines.append(t["ceiling"].format(ceiling=money(r.ceiling), base=money(r.base)))
    if "under_one_year" in r.warnings:
        lines.append(t["under_one_year"])
    else:
        lines.append(t["severance"].format(base=money(r.base),
                                           years_decimal=f"{years:.4f}".replace(".", ","),
                                           severance=money(r.severance)))
        lines.append(t["stamp"].format(stamp=money(r.stamp_duty),
                                       net=money(r.severance - r.stamp_duty)))
    daily = (r.monthly / 30).quantize(Decimal("0.01"))
    lines.append(t["notice"].format(weeks=r.notice_weeks, daily=money(daily),
                                    days=r.notice_weeks * 7, notice=money(r.notice)))
    lines.append(t["condition"])
    return "\n".join(lines)
