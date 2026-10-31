"""An interest calculation written out stretch by stretch, as the source the answer cites."""

from __future__ import annotations

from datetime import date

from legal_api.calc.interest import Interest, _known_until, _rates
from legal_api.calc.severance_text import money
from legal_api.locale import calculation_terms


def _day(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _rate(r) -> str:
    return f"{r:g}".replace(".", ",")


def render(results: list[Interest]) -> str:
    t = calculation_terms()["interest"]
    first = results[0]
    lines = [t["title"], t["basis"].format(principal=money(first.principal), start=_day(first.start),
                                           end=_day(first.end))]
    if len(results) > 1:
        lines.append(t["both"])
    for r in results:
        lines += ["", t[f"kind_{r.kind}"]]
        lines += [t["stretch"].format(start=_day(s.start), end=_day(s.end), days=s.days,
                                      rate=_rate(s.rate), interest=money(s.interest))
                  for s in r.stretches]
        lines.append(t["total"].format(total=money(r.total), sum=money(r.total + r.principal)))
        if "before_rates" in r.warnings:
            lines.append(t["before_rates"].format(first=_day(_rates(r.kind)[0][0])))
        if "after_known" in r.warnings:
            lines.append(t["after_known"].format(known=_day(_known_until())))
    return "\n".join(lines)
