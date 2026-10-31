"""The lawyer's calendar as a source: the deadlines they recorded in their cases, read when a
question is about them ("what is due this week?", "when is the next deadline here?").

It is given to the writer as a cited source like a calculation, so dates and case names in
the answer are checked against it, and the lawyer can open the list the answer came from.
In a case's chat only that case's deadlines are given, done ones too, so an answer there
does not bring in another case's deadline; elsewhere, the open deadlines of open cases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.agent.sources import Source
from legal_api.db.matter_models import Matter, MatterDeadline
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


def render(rows: list[tuple[MatterDeadline, Matter]], today: date,
           matter: Matter | None = None) -> str:
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
    t = matter_terms()["agenda"]
    citation = (t["citation_matter"].format(client=matter.client) if matter is not None
                else t["citation"])
    return Agenda(render(rows, today or date.today(), matter), citation,
                  f"agenda:{matter.id if matter else 'all'}")
