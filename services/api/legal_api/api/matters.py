"""Case files: create and edit them, see everything in one, keep its deadlines, and the
calendar of every open file's deadlines."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from legal_api.api.files import FileOut, file_out
from legal_api.auth import DB, CurrentUser
from legal_api.calc.calendar import calendar as official_calendar
from legal_api.calc.notice import Branch
from legal_api.db.app_models import Chat
from legal_api.db.matter_models import Matter, MatterDeadline
from legal_api.files import store
from legal_api.matters.search import search_matters
from legal_api.matters.service import chats_of, deadlines_of, drafts_of, files_of, owned

router = APIRouter(tags=["matters"])


class MatterIn(BaseModel):
    client: str = Field(min_length=1, max_length=200)
    subject: str = Field(default="", max_length=200)
    opponent: str = Field(default="", max_length=200)
    court: str = Field(default="", max_length=200)
    case_no: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=20000)


class MatterPatch(BaseModel):
    client: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=200)
    opponent: str | None = Field(default=None, max_length=200)
    court: str | None = Field(default=None, max_length=200)
    case_no: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=20000)
    closed: bool | None = None


class DeadlineIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    due: date
    branch: Branch | None = None
    message_id: uuid.UUID | None = None


class DeadlinePatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    due: date | None = None
    branch: Branch | None = None
    done: bool | None = None


class DeadlineOut(BaseModel):
    id: str
    matter_id: str
    label: str
    due: date
    done: bool
    branch: Branch | None
    message_id: str | None


class MatterOut(BaseModel):
    id: str
    client: str
    subject: str
    opponent: str
    court: str
    case_no: str
    notes: str
    closed: bool
    updated_at: datetime
    next_deadline: DeadlineOut | None = None


class ChatRef(BaseModel):
    id: str
    title: str
    updated_at: datetime


class DraftRef(BaseModel):
    id: str
    chat_id: str | None
    title: str
    petition_type: str
    updated_at: datetime


class MatterDetail(MatterOut):
    chats: list[ChatRef]
    documents: list[FileOut]
    drafts: list[DraftRef]
    deadlines: list[DeadlineOut]


class CalendarItem(DeadlineOut):
    client: str
    subject: str


class ChatMatter(BaseModel):
    matter_id: uuid.UUID | None


def _deadline_out(d: MatterDeadline) -> DeadlineOut:
    return DeadlineOut(id=str(d.id), matter_id=str(d.matter_id), label=d.label, due=d.due,
                       done=d.done, branch=d.branch, message_id=str(d.message_id) if d.message_id else None)


def _next(deadlines: list[MatterDeadline]) -> DeadlineOut | None:
    today = date.today()
    upcoming = [d for d in deadlines if not d.done and d.due >= today]
    overdue = [d for d in deadlines if not d.done and d.due < today]
    pick = (overdue or upcoming)[:1]
    return _deadline_out(pick[0]) if pick else None


def _matter_out(m: Matter, deadlines: list[MatterDeadline]) -> MatterOut:
    return MatterOut(id=str(m.id), client=m.client, subject=m.subject, opponent=m.opponent,
                     court=m.court, case_no=m.case_no, notes=m.notes, closed=m.closed,
                     updated_at=m.updated_at, next_deadline=_next(deadlines))


async def _matter(db, user, matter_id: uuid.UUID) -> Matter:
    matter = await owned(db, user.id, matter_id)
    if matter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "matter not found")
    return matter


async def _deadline(db, user, deadline_id: uuid.UUID) -> MatterDeadline:
    d = await db.get(MatterDeadline, deadline_id)
    if d is None or await owned(db, user.id, d.matter_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deadline not found")
    return d


def _touch(matter: Matter) -> None:
    matter.updated_at = datetime.now(UTC)


@router.get("/matters")
async def list_matters(user: CurrentUser, db: DB) -> list[MatterOut]:
    matters = (await db.scalars(select(Matter).where(Matter.user_id == user.id)
                                .order_by(Matter.closed, Matter.updated_at.desc()))).all()
    deadlines = await deadlines_of(db, [m.id for m in matters])
    return [_matter_out(m, [d for d in deadlines if d.matter_id == m.id]) for m in matters]


@router.post("/matters", status_code=status.HTTP_201_CREATED)
async def create_matter(body: MatterIn, user: CurrentUser, db: DB) -> MatterOut:
    now = datetime.now(UTC)
    matter = Matter(user_id=user.id, created_at=now, updated_at=now, **body.model_dump())
    db.add(matter)
    await db.commit()
    return _matter_out(matter, [])


@router.get("/matters/search")
async def search(q: str, user: CurrentUser, db: DB) -> dict:
    """Files and the documents in them that contain every typed term."""
    return await search_matters(db, user.id, q)


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: uuid.UUID, user: CurrentUser, db: DB) -> MatterDetail:
    m = await _matter(db, user, matter_id)
    deadlines = await deadlines_of(db, [m.id])
    chats = await chats_of(db, m.id)
    files = await files_of(db, m.id)
    titles = {c.id: c.title for c in chats}
    return MatterDetail(
        **_matter_out(m, deadlines).model_dump(),
        chats=[ChatRef(id=str(c.id), title=c.title, updated_at=c.updated_at) for c in chats],
        documents=[file_out(f, titles.get(f.chat_id)) for f in files],
        drafts=[DraftRef(id=str(d.id), chat_id=str(d.chat_id) if d.chat_id else None,
                         title=d.title, petition_type=d.petition_type, updated_at=d.updated_at)
                for d in await drafts_of(db, m.id)],
        deadlines=[_deadline_out(d) for d in deadlines])


@router.patch("/matters/{matter_id}")
async def edit_matter(matter_id: uuid.UUID, body: MatterPatch, user: CurrentUser,
                      db: DB) -> MatterOut:
    m = await _matter(db, user, matter_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(m, key, value)
    _touch(m)
    await db.commit()
    return _matter_out(m, await deadlines_of(db, [m.id]))


@router.delete("/matters/{matter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_matter(matter_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    """The file goes with its deadlines; its chats and documents stay, outside any file."""
    await db.delete(await _matter(db, user, matter_id))
    await db.commit()


@router.post("/matters/{matter_id}/files", status_code=status.HTTP_201_CREATED)
async def add_document(matter_id: uuid.UUID, user: CurrentUser, db: DB,
                       file: Annotated[UploadFile, File()]) -> FileOut:
    m = await _matter(db, user, matter_id)
    try:
        stored = await store.save(db, user.id, file.filename or "file", await file.read(),
                                  "upload", file.content_type, matter_id=m.id)
    except store.FileTooLarge as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large") from e
    except store.QuotaExceeded as e:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "storage full") from e
    _touch(m)
    await db.commit()
    return file_out(stored)


@router.post("/matters/{matter_id}/deadlines", status_code=status.HTTP_201_CREATED)
async def add_deadline(matter_id: uuid.UUID, body: DeadlineIn, user: CurrentUser,
                       db: DB) -> DeadlineOut:
    m = await _matter(db, user, matter_id)
    d = MatterDeadline(matter_id=m.id, label=body.label, due=body.due, branch=body.branch,
                       message_id=body.message_id, created_at=datetime.now(UTC))
    db.add(d)
    _touch(m)
    await db.commit()
    return _deadline_out(d)


@router.patch("/deadlines/{deadline_id}")
async def edit_deadline(deadline_id: uuid.UUID, body: DeadlinePatch, user: CurrentUser,
                        db: DB) -> DeadlineOut:
    d = await _deadline(db, user, deadline_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(d, key, value)
    await db.commit()
    return _deadline_out(d)


@router.delete("/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deadline(deadline_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await db.delete(await _deadline(db, user, deadline_id))
    await db.commit()


@router.get("/deadlines")
async def calendar(user: CurrentUser, db: DB) -> list[CalendarItem]:
    """Every deadline of the lawyer's open files, soonest first (done ones included, so the
    calendar can show what was met)."""
    rows = (await db.execute(
        select(MatterDeadline, Matter).join(Matter, Matter.id == MatterDeadline.matter_id)
        .where(Matter.user_id == user.id, Matter.closed.is_(False))
        .order_by(MatterDeadline.due))).all()
    return [CalendarItem(**_deadline_out(d).model_dump(), client=m.client, subject=m.subject)
            for d, m in rows]


@router.put("/chats/{chat_id}/matter")
async def move_chat(chat_id: uuid.UUID, body: ChatMatter, user: CurrentUser, db: DB) -> dict:
    """Put a chat in a file, or take it out (matter_id null)."""
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")
    if body.matter_id is not None:
        _touch(await _matter(db, user, body.matter_id))
    chat.matter_id = body.matter_id
    await db.commit()
    return {"id": str(chat.id), "matter_id": str(chat.matter_id) if chat.matter_id else None}


class Holiday(BaseModel):
    day: date
    name: str
    half: bool          # an eve, closed from 13:00


class CalendarYear(BaseModel):
    year: int
    covered: bool       # whether the year's religious holidays are listed
    holidays: list[Holiday]
    recess_start: date
    recess_end: date


@router.get("/holidays/{year}")
async def holidays(year: int, user: CurrentUser) -> CalendarYear:
    """Official holidays, half-day eves and the judicial recess of a year, as the period
    calculator knows them (calc/calendar.py), for the calendar to show."""
    cal = official_calendar()
    days = [Holiday(day=d, name=n, half=False) for d, n in cal.holidays.items() if d.year == year]
    days += [Holiday(day=d, name=n, half=True) for d, n in cal.half_days.items() if d.year == year]
    (sm, sd), (em, ed) = cal.recess
    return CalendarYear(year=year, covered=year in cal.covered_years,
                        holidays=sorted(days, key=lambda h: h.day),
                        recess_start=date(year, sm, sd), recess_end=date(year, em, ed))
