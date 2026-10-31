"""When a procedural period ends, computed in code, never by the model.

The rules (civil procedure; cited to the lawyer from the statute text the answer fetches):
- a period in days starts the day after notice, so it ends `amount` days after it; one in
  weeks, months or years ends on the day of the same name or number (a month that has no
  such day ends on its last day);
- a period that would end in the judicial recess (20 July - 31 August) is extended to one
  week after the recess ends, for matters the recess applies to (calc/sources.py gives
  both results whenever the recess changes the last day);
- a period whose last day is a weekend or an official holiday ends on the next working day;
- a last day on a half-day eve is flagged for the lawyer to check rather than decided here;
- a date in a year whose religious holidays are not listed is flagged, never assumed.
"""

from __future__ import annotations

import calendar as months
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from legal_api.calc.calendar import calendar

Unit = Literal["day", "week", "month", "year"]
UNITS: tuple[Unit, ...] = ("day", "week", "month", "year")


@dataclass
class Deadline:
    start: date
    amount: int
    unit: Unit
    end: date
    recess: bool                                   # the judicial recess rule was applied
    steps: list[tuple[str, dict]] = field(default_factory=list)      # (code, values)
    warnings: list[tuple[str, dict]] = field(default_factory=list)   # (code, values)


def add_period(start: date, amount: int, unit: Unit) -> date:
    if unit == "day":
        return start + timedelta(days=amount)
    if unit == "week":
        return start + timedelta(weeks=amount)
    months_ahead = amount * (12 if unit == "year" else 1)
    year, month = divmod(start.month - 1 + months_ahead, 12)
    year, month = start.year + year, month + 1
    return date(year, month, min(start.day, months.monthrange(year, month)[1]))


def compute(start: date, amount: int, unit: Unit, recess: bool,
            extension: int | None = None) -> Deadline:
    """`extension`: days added after the recess ends (by default the civil rule's week)."""
    cal = calendar()
    end = add_period(start, amount, unit)
    result = Deadline(start, amount, unit, end, recess)
    result.steps.append(("period", {"end": end}))
    if recess and cal.in_recess(end):
        end = cal.recess_end(end.year) + timedelta(
            days=cal.recess_extension if extension is None else extension)
        result.steps.append(("recess", {"end": end}))
    if not cal.covered(end) or not cal.covered(start):
        result.warnings.append(("not_covered", {"year": end.year}))
    elif not cal.is_working_day(end):
        reason = cal.holidays.get(end)
        shifted = cal.next_working_day(end)
        result.steps.append(("holiday" if reason else "weekend",
                             {"day": end, "name": reason or "", "end": shifted}))
        end = shifted
    if end in cal.half_days:
        result.warnings.append(("half_day", {"day": end, "name": cal.half_days[end]}))
    result.end = end
    return result
