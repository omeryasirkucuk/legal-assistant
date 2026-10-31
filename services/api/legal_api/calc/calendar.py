"""Days on which a period cannot end: weekends, official holidays, half-day eves, and the
judicial recess, from locales/tr/calendar.json (each value there with its source).

Religious holidays move every year and are listed per year; a date in a year that is not
listed is reported as not covered rather than treated as a working day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache

from legal_api.locale import calendar_data


@dataclass(frozen=True)
class Calendar:
    holidays: dict[date, str]          # full-day holidays -> name
    half_days: dict[date, str]         # eves, closed from 13:00 -> name
    covered_years: frozenset[int]
    recess: tuple[tuple[int, int], tuple[int, int]]   # (month, day) start and end
    recess_extension: int

    def covered(self, d: date) -> bool:
        return d.year in self.covered_years

    def is_working_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def next_working_day(self, d: date) -> date:
        while not self.is_working_day(d):
            d += timedelta(days=1)
        return d

    def in_recess(self, d: date) -> bool:
        (sm, sd), (em, ed) = self.recess
        return date(d.year, sm, sd) <= d <= date(d.year, em, ed)

    def recess_end(self, year: int) -> date:
        em, ed = self.recess[1]
        return date(year, em, ed)


@cache
def calendar() -> Calendar:
    data = calendar_data()
    years = frozenset(data["covered_years"])
    holidays: dict[date, str] = {}
    half: dict[date, str] = {}
    for year in years:
        for h in data["fixed"]:
            holidays[date(year, h["month"], h["day"])] = h["name"]
        for h in data["fixed_half_days"]:
            half[date(year, h["month"], h["day"])] = h["name"]
    for r in data["religious"]:
        half[date.fromisoformat(r["eve"])] = f"{r['name']} arifesi"
        for d in r["days"]:
            holidays[date.fromisoformat(d)] = r["name"]
    recess = data["judicial_recess"]
    return Calendar(holidays, half, years,
                    ((recess["start"]["month"], recess["start"]["day"]),
                     (recess["end"]["month"], recess["end"]["day"])),
                    recess["extension_days"])
