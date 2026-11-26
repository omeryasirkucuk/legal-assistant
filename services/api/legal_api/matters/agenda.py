"""Saved deadlines and events as a cited source for calendar questions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.agent.sources import Source
from legal_api.db.matter_models import ISTANBUL, CalendarEvent, Matter, MatterDeadline
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import calculation_terms, matter_terms

MAX_LINES = 60


def _state(d: MatterDeadline, today: date) -> str:
    t = matter_terms()["agenda"]
    if d.done:
        return t["done"]
    days = (d.due - today).days
    if days == 0:
        return t["today"]
    return t["left"].format(days=days) if days > 0 else t["passed"].format(days=-days)


def _line(d: MatterDeadline, matter: Matter | None, today: date) -> str:
    t = matter_terms()["agenda"]
    state = _state(d, today)
    if d.branch in t["branches"]:
        state += ", " + t["branch"].format(branch=t["branches"][d.branch])
    fields = {"due": d.due.strftime("%d.%m.%Y"), "label": d.label, "state": state,
              "weekday": calculation_terms()["weekdays"][d.due.weekday()]}
    if matter is None:
        return t["line_matter"].format(**fields)
    name = matter.client + (f", {matter.case_no}" if matter.case_no else "")
    return t["line"].format(**fields, matter=name)


def _listing(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return [*lines[:MAX_LINES], matter_terms()["agenda"]["more"].format(
        count=len(lines) - MAX_LINES)]


def _event_line(event: CalendarEvent, matter: Matter | None) -> str:
    t = matter_terms()["agenda"]
    day = event.due.strftime("%d.%m.%Y")
    weekday = calculation_terms()["weekdays"][event.due.weekday()]
    time = event.start_time.strftime("%H:%M") if event.start_time else t["all_day"]
    if event.end_time:
        time += "–" + event.end_time.strftime("%H:%M")
    parts = [f"{day} {weekday} {time}", t["kinds"][event.kind], event.label]
    if matter is not None:
        parts.append(matter.client + (f", {matter.case_no}" if matter.case_no else ""))
    if event.done:
        parts.append(t["done"])
    return " · ".join(parts)


def render(rows: list[tuple[MatterDeadline, Matter]], today: date,
           matter: Matter | None = None,
           events: list[tuple[CalendarEvent, Matter | None]] | None = None) -> str:
    """`rows`: deadlines with their cases, by date; `matter`: the case the chat is in."""
    t = matter_terms()["agenda"]
    weekday = calculation_terms()["weekdays"][today.weekday()]
    out = [t["title"].format(today=today.strftime("%d.%m.%Y"), weekday=weekday), ""]
    if matter is not None:
        own = [_line(d, None, today) for d, m in rows if m.id == matter.id]
        out += [t["this_matter"].format(client=matter.client),
                *(_listing(own) or [t["none_matter"]])]
    else:
        open_ = [_line(d, m, today) for d, m in rows if not d.done]
        out += [t["open"], *(_listing(open_) or [t["none"]])]
    if events is not None:
        lines = [_event_line(event, linked if matter is None else None)
                 for event, linked in events
                 if (not event.done if matter is None else event.matter_id == matter.id)]
        out += ["", t["events"], *(_listing(lines) or [t["none_events"]])]
    return "\n".join(out).strip()


async def load(db: AsyncSession, user_id: uuid.UUID,
               matter_id: uuid.UUID | None = None) -> list[tuple[MatterDeadline, Matter]]:
    """Every deadline of the chat's case; outside a case, open deadlines of open cases."""
    query = (select(MatterDeadline, Matter).join(Matter, Matter.id == MatterDeadline.matter_id)
             .where(Matter.user_id == user_id).order_by(MatterDeadline.due))
    if matter_id is not None:
        query = query.where(Matter.id == matter_id)
    else:
        query = query.where(MatterDeadline.done.is_(False), Matter.closed.is_(False))
    return [(d, m) for d, m in (await db.execute(query)).all()]


@dataclass(frozen=True)
class Agenda:
    """The calendar as the chat reads it, made into a source only if the question needs it."""
    text: str
    citation: str
    source_id: str

    def source(self, ledger: EvidenceLedger) -> Source:
        evidence = ledger.add_calculation(source_id=self.source_id, citation=self.citation,
                                          text=self.text)
        return Source(evidence, self.text)


async def agenda(db: AsyncSession, user_id: uuid.UUID, matter: Matter | None = None,
                 today: date | None = None) -> Agenda:
    rows = await load(db, user_id, matter.id if matter else None)
    events = (select(CalendarEvent, Matter).outerjoin(
        Matter, (Matter.id == CalendarEvent.matter_id) & (Matter.user_id == user_id))
        .where(CalendarEvent.user_id == user_id)
        .order_by(CalendarEvent.due, CalendarEvent.start_time.nulls_first(), CalendarEvent.id))
    if matter is not None:
        events = events.where(CalendarEvent.matter_id == matter.id)
    else:
        events = events.where(CalendarEvent.done.is_(False))
    event_rows = [(event, linked) for event, linked in (await db.execute(events)).all()]
    t = matter_terms()["agenda"]
    citation = (t["citation_matter"].format(client=matter.client) if matter is not None
                else t["citation"])
    return Agenda(render(rows, today or datetime.now(ISTANBUL).date(),
                         matter, event_rows), citation,
                  f"agenda:{matter.id if matter else 'all'}")
