"""Account-owned calendar entries and in-app reminders."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select

from legal_api.auth import DB, CurrentUser
from legal_api.db.matter_models import ISTANBUL, CalendarEvent, Matter
from legal_api.matters.ical import event_ical

router = APIRouter(prefix="/calendar", tags=["calendar"])

ALL_DAY_REMINDER = time(9)
Kind = Literal["hearing", "meeting", "reminder", "event"]


class EventIn(BaseModel):
    kind: Kind
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    due: date = Field(ge=date(1900, 1, 1), le=date(9999, 12, 30))
    matter_id: uuid.UUID | None = None
    start_time: time | None = None
    end_time: time | None = None
    location: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=10000)
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        for value in (self.start_time, self.end_time):
            if value is not None and (value.tzinfo or value.second or value.microsecond):
                raise ValueError("use local time with minute precision")
        if self.end_time is not None and (
            self.start_time is None or self.end_time <= self.start_time
        ):
            raise ValueError("end time must follow start time")
        return self

    def reminder_at(self) -> datetime | None:
        if self.reminder_minutes is None:
            return None
        start = datetime.combine(self.due, self.start_time or ALL_DAY_REMINDER, ISTANBUL)
        return start.astimezone(UTC) - timedelta(minutes=self.reminder_minutes)


class EventOut(EventIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    done: bool
    remind_at: datetime | None
    reminder_dismissed: bool


class EventStatus(BaseModel):
    done: bool | None = None
    dismiss_reminder_at: datetime | None = None


class DueReminder(BaseModel):
    id: uuid.UUID
    label: str
    due: date
    remind_at: datetime


async def _event(db: DB, user: CurrentUser, event_id: uuid.UUID, *,
                 lock: bool = False) -> CalendarEvent:
    query = select(CalendarEvent).where(
        CalendarEvent.id == event_id, CalendarEvent.user_id == user.id)
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return row


async def _check_matter(db: DB, user: CurrentUser, matter_id: uuid.UUID | None) -> None:
    if matter_id is None:
        return
    linked = await db.scalar(select(Matter.id).where(
        Matter.id == matter_id, Matter.user_id == user.id).with_for_update(read=True, key_share=True))
    if linked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "matter not found")


@router.get("/events")
async def list_events(user: CurrentUser, db: DB) -> list[EventOut]:
    return (await db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == user.id)
                            .order_by(CalendarEvent.due, CalendarEvent.start_time.nulls_first(),
                                      CalendarEvent.id))).all()


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(body: EventIn, user: CurrentUser, db: DB) -> EventOut:
    await _check_matter(db, user, body.matter_id)
    row = CalendarEvent(user_id=user.id, **body.model_dump(), remind_at=body.reminder_at())
    db.add(row)
    await db.commit()
    return row


@router.get("/events/{event_id}/ics")
async def download_event(event_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    row = await _event(db, user, event_id)
    return Response(event_ical(row), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="takvim.ics"',
                             "Cache-Control": "private, no-store"})


@router.put("/events/{event_id}")
async def edit_event(event_id: uuid.UUID, body: EventIn, user: CurrentUser, db: DB) -> EventOut:
    # Match the case deletion lock order before taking the event lock.
    await _check_matter(db, user, body.matter_id)
    row = await _event(db, user, event_id, lock=True)
    remind_at = body.reminder_at()
    if remind_at != row.remind_at:
        row.reminder_dismissed = False
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.remind_at = remind_at
    await db.commit()
    return row


@router.patch("/events/{event_id}")
async def update_status(event_id: uuid.UUID, body: EventStatus, user: CurrentUser,
                        db: DB) -> EventOut:
    row = await _event(db, user, event_id, lock=True)
    if body.done is not None:
        row.done = body.done
    if body.dismiss_reminder_at is not None and body.dismiss_reminder_at == row.remind_at:
        row.reminder_dismissed = True
    await db.commit()
    return row


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await db.delete(await _event(db, user, event_id, lock=True))
    await db.commit()


@router.get("/reminders")
async def due_reminders(user: CurrentUser, db: DB) -> list[DueReminder]:
    rows = (await db.execute(select(CalendarEvent.id, CalendarEvent.label, CalendarEvent.due,
                                    CalendarEvent.remind_at)
            .where(CalendarEvent.user_id == user.id, CalendarEvent.done.is_(False),
                   CalendarEvent.reminder_dismissed.is_(False),
                   CalendarEvent.remind_at <= datetime.now(UTC))
            .order_by(CalendarEvent.remind_at, CalendarEvent.id))).all()
    return [DueReminder(id=id_, label=label, due=due, remind_at=remind_at)
            for id_, label, due, remind_at in rows]
