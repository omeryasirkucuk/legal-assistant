"""Drafting: the lawyer's sample petitions, the style learnt from them, and drafts."""

from __future__ import annotations

import asyncio
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from legal_api import llm
from legal_api.auth import DB, CurrentUser
from legal_api.chat.service import spent_today
from legal_api.config import get_settings
from legal_api.db.drafting_models import Draft, StyleMemory, StyleSample
from legal_api.db.file_models import StoredFile
from legal_api.drafting import memory, store
from legal_api.drafting.adjust import RewriteRejected, rewrite
from legal_api.drafting.export import FORMATS, MEDIA_TYPES
from legal_api.drafting.export_pdf import NoFont
from legal_api.drafting.feedback import ACTIONS, apply_action, learn_from_edit
from legal_api.drafting.files import draft_file, file_name, refresh_draft_file
from legal_api.drafting.locate import locate
from legal_api.drafting.rich import BadDocument, apply_doc, carry_over, editor_doc, fingerprint
from legal_api.drafting.sample_profile import SampleProfile, analyze
from legal_api.drafting.style import petition_span
from legal_api.drafting.tidy import tidy
from legal_api.drafting.types import petition_types
from legal_api.files.extract import UnsupportedFile, text_of
from legal_api.files.labels import file_format
from legal_api.files.store import QuotaExceeded
from legal_api.files.store import read as read_file
from legal_api.spend import record_spend

router = APIRouter(tags=["drafting"])
_background: set[asyncio.Task] = set()
MIN_SAMPLE_WORDS = 80


class SampleOut(BaseModel):
    id: str
    title: str
    petition_type: str | None
    area: str           # area of law as the model read it, "other" if unclear
    matter: str         # the matter in a few words ("uncontested divorce")
    format: str         # word, udf, pdf, text, ... from the file name
    words: int
    created_at: datetime


class SampleType(BaseModel):
    petition_type: str | None


class SampleText(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)
    petition_type: str | None = None


class Rules(BaseModel):
    rules: list[str] = Field(max_length=store.MAX_RULES)


class StyleChoice(BaseModel):
    length: str | None = None      # short | medium | long, or None to follow the samples
    register: str | None = None    # plain | balanced | formal, or None to follow the samples


class DraftOut(BaseModel):
    id: str
    format: str
    file_name: str
    chat_id: str | None
    message_id: str | None
    petition_type: str
    title: str
    text: str
    doc: dict                         # the petition as the editor holds it (drafting/rich.py)
    updated_at: datetime


class DraftText(BaseModel):
    """Either the whole text, or the petition as the editor's document."""
    text: str | None = Field(default=None, min_length=1, max_length=400_000)
    doc: dict | None = None
    # An autosave while the lawyer types: kept, but the style is learnt once, when they
    # finish editing (POST /drafts/{id}/learn), not on every save.
    learn: bool = True


class Adjust(BaseModel):
    action: str
    # A passage to change instead of the whole draft: character offsets in the text, or the
    # passage as selected in the editor.
    start: int | None = None
    end: int | None = None
    selection: str | None = Field(default=None, max_length=200_000)


def _sample_out(s: StyleSample) -> SampleOut:
    return SampleOut(id=str(s.id), title=s.title, petition_type=s.petition_type,
                     area=SampleProfile.of(s.profile).area,
                     matter=SampleProfile.of(s.profile).matter, format=file_format(s.title),
                     words=int(s.style.get("words", 0)), created_at=s.created_at)


def _draft_out(d: Draft) -> DraftOut:
    fmt = d.meta.get("format", "docx")
    return DraftOut(id=str(d.id), format=fmt, file_name=file_name(d.title, fmt), chat_id=str(d.chat_id) if d.chat_id else None,
                    message_id=d.meta.get("message_id"),
                    petition_type=d.petition_type, title=d.title, text=d.text,
                    doc=editor_doc(d), updated_at=d.updated_at)


async def _owned_draft(db, user, draft_id: uuid.UUID) -> Draft:
    draft = await db.get(Draft, draft_id)
    if draft is None or draft.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return draft


@router.get("/drafting/types")
async def list_types(user: CurrentUser) -> list[dict]:
    return [{"id": t.id, "name": t.name} for t in petition_types().values()]


@router.get("/drafting/samples")
async def list_samples(user: CurrentUser, db: DB) -> list[SampleOut]:
    await store.read_unread_samples(db, user.id)
    return [_sample_out(s) for s in await store.samples_of(db, user.id)]


async def _add(db, user, title: str, text: str, petition_type: str | None,
               replace: uuid.UUID | None = None, keep: bool = False) -> SampleOut:
    """A sample, read by the model (sample_profile): its petition type is taken from that
    reading when not given. Errors name the reason (detail): too_short, duplicate (already a
    sample), not_petition (a decision or contract would teach a wrong style), or
    {"code": "similar", "id", "title"} when it looks like an edited copy of a sample: the
    lawyer then sends it again with `replace` (the old one goes) or `keep` (both stay).
    That is asked before the model reads it, so a question costs nothing."""
    if len(text.split()) < MIN_SAMPLE_WORDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "too_short")
    if await store.has_sample_text(db, user.id, text):
        raise HTTPException(status.HTTP_409_CONFLICT, "duplicate")
    old = await db.get(StyleSample, replace) if replace else None
    if old is not None and old.user_id != user.id:
        old = None
    if old is None and not keep:
        similar = await store.similar_sample(db, user.id, text)
        if similar:
            raise HTTPException(status.HTTP_409_CONFLICT, {
                "code": "similar", "id": str(similar[0].id), "title": similar[0].title})
    read_usage = llm.Usage()
    profile = await analyze(title, text, read_usage)
    await record_spend(db, user.id, "sample_read", read_usage)
    await db.commit()
    if not profile.is_petition and not petition_type:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not_petition")
    sample = await store.add_sample(db, user.id, title, text,
                                    petition_type or profile.petition_type or (
                                        old.petition_type if old else None), profile)
    if old is not None:
        await db.delete(old)
        await db.commit()
    return _sample_out(sample)


@router.post("/drafting/samples", status_code=status.HTTP_201_CREATED)
async def upload_sample(user: CurrentUser, db: DB, file: Annotated[UploadFile, File()],
                        petition_type: Annotated[str | None, Form()] = None,
                        replace: Annotated[uuid.UUID | None, Form()] = None,
                        keep: Annotated[bool, Form()] = False) -> SampleOut:
    """A petition the lawyer wrote (Word, UYAP, PDF, OpenDocument, RTF or text), to learn
    their style from."""
    try:
        text = text_of(file.filename or "", await file.read())
    except UnsupportedFile as e:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported") from e
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        # A damaged file (a UYAP or Word file that is not a valid archive) is not a crash.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unreadable") from e
    if not text.strip():
        # A scanned page (an image or an image-only PDF) has no text to learn from.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no_text")
    return await _add(db, user, file.filename or "petition", text, petition_type, replace, keep)


@router.post("/drafting/samples/text", status_code=status.HTTP_201_CREATED)
async def paste_sample(body: SampleText, user: CurrentUser, db: DB) -> SampleOut:
    return await _add(db, user, body.title, body.text, body.petition_type)


@router.put("/drafting/samples/{sample_id}")
async def set_sample_type(sample_id: uuid.UUID, body: SampleType, user: CurrentUser,
                          db: DB) -> SampleOut:
    """The lawyer corrects the petition type worked out for a sample."""
    sample = await db.get(StyleSample, sample_id)
    if sample is None or sample.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sample not found")
    sample.petition_type = body.petition_type if body.petition_type in petition_types() else None
    await db.commit()
    return _sample_out(sample)


@router.delete("/drafting/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(sample_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    sample = await db.get(StyleSample, sample_id)
    if sample is None or sample.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sample not found")
    await db.delete(sample)
    await db.commit()


@router.get("/drafting/profile")
async def get_profile(user: CurrentUser, db: DB) -> dict:
    return store.summary(await store.style_book(db, user.id))


@router.put("/drafting/profile/style")
async def put_style(body: StyleChoice, user: CurrentUser, db: DB) -> dict:
    await store.choose_style(db, user.id, body.length, body.register)
    return store.summary(await store.style_book(db, user.id))


@router.put("/drafting/profile/rules")
async def put_rules(body: Rules, user: CurrentUser, db: DB) -> dict:
    return {"rules": await store.set_rules(db, user.id, body.rules)}


@router.get("/drafting/memories")
async def list_memories(user: CurrentUser, db: DB) -> list[dict]:
    """What was learnt from the lawyer's edits; `used` once seen in enough separate edits."""
    rows = (await db.scalars(select(StyleMemory).where(StyleMemory.user_id == user.id)
                             .order_by(StyleMemory.seen.desc(), StyleMemory.updated_at.desc()))).all()
    return [{"id": str(m.id), "text": m.text, "seen": m.seen, "used": m.seen >= memory.MIN_SEEN}
            for m in rows]


@router.delete("/drafting/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    m = await db.get(StyleMemory, memory_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    await db.delete(m)
    await db.commit()


@router.post("/drafting/profile/reset")
async def reset_profile(user: CurrentUser, db: DB) -> dict:
    """Forget everything learnt; the lawyer's own petitions and written wishes stay."""
    await store.reset_learning(db, user.id)
    return store.summary(await store.style_book(db, user.id))


@router.get("/drafts")
async def list_drafts(user: CurrentUser, db: DB, chat_id: uuid.UUID | None = None
                      ) -> list[DraftOut]:
    query = select(Draft).where(Draft.user_id == user.id)
    if chat_id:
        query = query.where(Draft.chat_id == chat_id)
    rows = (await db.scalars(query.order_by(Draft.updated_at.desc()).limit(50))).all()
    return [_draft_out(d) for d in rows]


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: uuid.UUID, user: CurrentUser, db: DB) -> DraftOut:
    return _draft_out(await _owned_draft(db, user, draft_id))


@router.put("/drafts/{draft_id}")
async def save_draft(draft_id: uuid.UUID, body: DraftText, user: CurrentUser, db: DB
                     ) -> DraftOut:
    """The lawyer's edited text; how they changed it moves their style preferences."""
    draft = await _owned_draft(db, user, draft_id)
    if body.doc is not None:
        try:
            new_text = apply_doc(draft.text, body.doc)
        except BadDocument as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    elif body.text is not None:
        new_text = body.text
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to save")
    # Edits to a copy of the lawyer's own document say nothing about the drafts we write.
    own_document = "from_file" in draft.meta
    if body.learn and not own_document:
        await _learn(db, user.id, draft, draft.meta.get("learn_base", draft.text), new_text)
    elif not own_document and "learn_base" not in draft.meta:
        draft.meta = {**draft.meta, "learn_base": draft.text}     # the text before this session
    draft.text, draft.updated_at = new_text, datetime.now(UTC)
    if body.doc is not None:
        draft.meta = {**draft.meta, "doc": body.doc, "doc_for": fingerprint(new_text)}
    await db.commit()
    await refresh_draft_file(db, draft)
    return _draft_out(draft)


async def _learn(db, user_id: uuid.UUID, draft: Draft, before: str, after: str) -> None:
    """What the lawyer's edit shows about their style: preferences now, remembered habits
    after the response (a model reads the change), so saving does not wait."""
    book = await store.style_book(db, user_id)
    await store.set_preferences(db, user_id, learn_from_edit(book.preferences, before, after))
    task = asyncio.create_task(memory.learn_from_edit(user_id, before, after, draft.petition_type))
    _background.add(task)
    task.add_done_callback(_background.discard)
    draft.meta = {k: v for k, v in draft.meta.items() if k != "learn_base"}


@router.post("/drafts/{draft_id}/learn", status_code=status.HTTP_204_NO_CONTENT)
async def learn_from_session(draft_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    """The lawyer finished editing: learn once from all the autosaved changes."""
    draft = await _owned_draft(db, user, draft_id)
    before = draft.meta.get("learn_base")
    if before is None or "from_file" in draft.meta:
        return
    await _learn(db, user.id, draft, before, draft.text)
    await db.commit()


@router.post("/drafts/{draft_id}/adjust")
async def adjust_draft(draft_id: uuid.UUID, body: Adjust, user: CurrentUser, db: DB
                       ) -> DraftOut:
    if body.action not in ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown action")
    draft = await _owned_draft(db, user, draft_id)
    # Without a selection only the petition is rewritten; the note and checklist stay.
    whole = petition_span(draft.text)
    start = body.start if body.start is not None else whole[0]
    end = body.end if body.end is not None else whole[1]
    if body.selection:
        found = locate(draft.text, body.selection, whole)
        if found is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "selection not found")
        start, end = found
    if not 0 <= start < end <= len(draft.text):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad selection")
    if await spent_today(db, user.id) >= get_settings().daily_user_budget_usd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily budget reached")
    book = await store.style_book(db, user.id)
    usage = llm.Usage()
    try:
        part = await rewrite(draft.text[start:end], body.action, book.rules, usage)
    except RewriteRejected as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    before = editor_doc(draft)
    draft.text = tidy(draft.text[:start] + part + draft.text[end:])
    draft.updated_at = datetime.now(UTC)
    draft.meta = {**draft.meta,
                  "doc": carry_over(before, draft.text), "doc_for": fingerprint(draft.text),
                  "adjust_cost_usd": round(draft.meta.get("adjust_cost_usd", 0)
                                           + usage.cost_usd, 4)}
    await record_spend(db, user.id, "draft_adjust", usage)
    await store.set_preferences(db, user.id, apply_action(book.preferences, body.action))
    await db.commit()
    await refresh_draft_file(db, draft)
    return _draft_out(draft)


@router.get("/drafts/{draft_id}/file")
async def get_draft_file(draft_id: uuid.UUID, user: CurrentUser, db: DB,
                         format: str | None = None) -> Response:
    """The petition as a file, in the format chosen when it was written unless another is
    asked for; each format made is kept in the user's files."""
    draft = await _owned_draft(db, user, draft_id)
    fmt = format if format in FORMATS else draft.meta.get("format", "docx")
    try:
        stored = await draft_file(db, draft, fmt)
    except NoFont as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e
    except QuotaExceeded as e:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "storage full") from e
    return Response(read_file(stored), media_type=MEDIA_TYPES[fmt], headers={
        "Content-Disposition": f"attachment; filename=\"petition.{fmt}\"; "
                               f"filename*=UTF-8''{quote(stored.name)}"})


@router.post("/drafts/from-file/{file_id}")
async def edit_file(file_id: uuid.UUID, user: CurrentUser, db: DB) -> DraftOut:
    """A file opened in the editor: a petition's own draft, or for a document the lawyer
    added, an editable copy (made once and reopened after), so the original stays as it was."""
    f = await db.get(StoredFile, file_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    if f.draft_id:
        return _draft_out(await _owned_draft(db, user, f.draft_id))
    copy = await db.scalar(select(Draft).where(
        Draft.user_id == user.id, Draft.meta["from_file"].astext == str(f.id)))
    if copy is not None:
        return _draft_out(copy)
    if not (f.text or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no text to edit")
    now = datetime.now(UTC)
    fmt = "udf" if f.name.lower().endswith(".udf") else "pdf" if f.name.lower().endswith(".pdf") else "docx"
    copy = Draft(user_id=user.id, chat_id=f.chat_id, petition_type="other",
                 title=f.name.rsplit(".", 1)[0][:200], text=f.text, created_at=now,
                 updated_at=now, meta={"from_file": str(f.id), "format": fmt})
    db.add(copy)
    await db.commit()
    return _draft_out(copy)
