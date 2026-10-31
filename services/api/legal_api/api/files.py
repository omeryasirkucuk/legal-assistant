"""The user's files: upload attachments, list and manage them, see the space used."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from legal_api.api.folders import owned_folder
from legal_api.auth import DB, CurrentUser
from legal_api.config import get_settings
from legal_api.db.app_models import Chat
from legal_api.db.drafting_models import Draft
from legal_api.db.file_models import StoredFile
from legal_api.drafting.export import FORMATS, blocks
from legal_api.drafting.files import draft_file, refresh_draft_file
from legal_api.drafting.rich import editor_doc, to_doc
from legal_api.files import store
from legal_api.files.labels import file_format, labels
from legal_api.matters.service import owned as owned_matter

router = APIRouter(prefix="/files", tags=["files"])


class FileOut(BaseModel):
    id: str
    name: str
    media_type: str
    size: int
    origin: str
    format: str         # word, pdf, udf, image, spreadsheet, email, text, other
    kind: str           # petition, notice, decision, contract, ... or other
    area: str           # labour, tenancy, family, ... or other
    readable: bool
    chat_id: str | None
    chat_title: str | None
    draft_id: str | None      # the petition draft a generated file was made from
    folder_id: str | None     # the lawyer's folder in My files
    matter_id: str | None     # the case it was added to
    created_at: datetime


class FilePatch(BaseModel):
    """A new name, a folder (or the top level), or a case to use it in (or none)."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    folder_id: uuid.UUID | None = None
    to_top: bool = False
    matter_id: uuid.UUID | None = None
    no_matter: bool = False


def file_out(f: StoredFile, chat_title: str | None = None) -> FileOut:
    return FileOut(id=str(f.id), name=f.name, media_type=f.media_type, size=f.size,
                   origin=f.origin, format=file_format(f.name, f.media_type),
                   kind=f.kind or "other", area=f.area or "other", readable=bool(f.text) or f.media_type.startswith("image/"),
                   chat_id=str(f.chat_id) if f.chat_id else None, chat_title=chat_title,
                   draft_id=str(f.draft_id) if f.draft_id else None,
                   folder_id=str(f.folder_id) if f.folder_id else None,
                   matter_id=str(f.matter_id) if f.matter_id else None, created_at=f.created_at)


async def _owned(db, user, file_id: uuid.UUID) -> StoredFile:
    f = await db.get(StoredFile, file_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    return f


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(user: CurrentUser, db: DB, file: Annotated[UploadFile, File()],
                 folder_id: Annotated[uuid.UUID | None, Form()] = None) -> FileOut:
    """An attachment or a file added in My files: kept in the user's space, read and
    labelled; an attachment is linked to a message when sent."""
    if folder_id:
        await owned_folder(db, user.id, folder_id)
    try:
        stored = await store.save(db, user.id, file.filename or "file", await file.read(),
                                  "upload", file.content_type)
        stored.folder_id = folder_id
        await db.commit()
    except store.FileTooLarge as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large") from e
    except store.QuotaExceeded as e:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "storage full") from e
    return file_out(stored)


@router.get("")
async def list_files(user: CurrentUser, db: DB) -> list[FileOut]:
    rows = (await db.execute(
        select(StoredFile, Chat.title, Draft.petition_type)
        .outerjoin(Chat, Chat.id == StoredFile.chat_id)
        .outerjoin(Draft, Draft.id == StoredFile.draft_id)
        .where(StoredFile.user_id == user.id).order_by(StoredFile.created_at.desc()))).all()
    unlabelled = [(f, petition_type) for f, _, petition_type in rows if f.kind is None]
    for f, petition_type in unlabelled:     # files kept before labelling existed
        f.kind, f.area = labels(f.name, f.text, petition_type)
    if unlabelled:
        await db.commit()
    return [file_out(f, title) for f, title, _ in rows]


@router.get("/usage")
async def usage(user: CurrentUser, db: DB) -> dict:
    return {"used_bytes": await store.used_bytes(db, user.id),
            "quota_bytes": get_settings().user_storage_bytes}


@router.get("/{file_id}")
async def download(file_id: uuid.UUID, user: CurrentUser, db: DB,
                   inline: bool = False) -> Response:
    f = await _owned(db, user, file_id)
    kind = "inline" if inline else "attachment"
    return Response(store.read(f), media_type=f.media_type, headers={
        "Content-Disposition": f"{kind}; filename=\"file\"; filename*=UTF-8''{quote(f.name)}"})


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(file_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await store.delete(db, await _owned(db, user, file_id))


@router.patch("/{file_id}")
async def edit(file_id: uuid.UUID, body: FilePatch, user: CurrentUser, db: DB) -> FileOut:
    f = await _owned(db, user, file_id)
    if body.to_top:
        f.folder_id = None
    elif body.folder_id is not None:
        f.folder_id = (await owned_folder(db, user.id, body.folder_id)).id
    if body.no_matter:
        f.matter_id = None
    elif body.matter_id is not None:
        if await owned_matter(db, user.id, body.matter_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "matter not found")
        f.matter_id = body.matter_id
    await db.commit()
    if body.name is not None:
        f = await _rename(db, f, body.name)
    return file_out(f)


async def _rename(db, f: StoredFile, name: str) -> StoredFile:
    """A new name; the extension stays. A petition's file takes its name from the draft, so
    the draft is renamed and its files made again."""
    base = store.safe_name(name).rsplit(".", 1)[0].strip() if "." in name \
        else store.safe_name(name).strip()
    if not base:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty name")
    ext = f.name.rsplit(".", 1)[1] if "." in f.name else ""
    if f.draft_id:
        draft = await db.get(Draft, f.draft_id)
        draft.title = base[:200]
        folder = f.folder_id
        await db.commit()
        fmt = ext if ext in FORMATS else draft.meta.get("format", "docx")
        await refresh_draft_file(db, draft)
        made = await draft_file(db, draft, fmt)
        made.folder_id = folder
        await db.commit()
        return made
    f.name = f"{base}.{ext}" if ext else base
    await db.commit()
    return f


@router.get("/{file_id}/preview")
async def preview(file_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    """How the file is shown in the app: a PDF or image as it is, any other readable
    document as pages of text (a petition as its draft)."""
    f = await _owned(db, user, file_id)
    if f.media_type == "application/pdf":
        return {"kind": "pdf"}
    if f.media_type.startswith("image/"):
        return {"kind": "image"}
    if f.draft_id:
        draft = await db.get(Draft, f.draft_id)
        if draft is not None:
            return {"kind": "document", "doc": editor_doc(draft)}
    if (f.text or "").strip():
        return {"kind": "document", "doc": to_doc(blocks(f.text))}
    return {"kind": "none"}


class CopyTo(BaseModel):
    folder_id: uuid.UUID | None = None      # none: the top level


def _free_name(name: str, taken: set[str]) -> str:
    """The name, or with " (2)", " (3)"... before the extension when the folder has it."""
    if name not in taken:
        return name
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    n = 2
    while (candidate := f"{base} ({n}){'.' + ext if ext else ''}") in taken:
        n += 1
    return candidate


@router.post("/{file_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy(file_id: uuid.UUID, body: CopyTo, user: CurrentUser, db: DB) -> FileOut:
    """A copy in a folder: a file of its own (read and labelled again, in no chat or case),
    counted in the user's space."""
    f = await _owned(db, user, file_id)
    if body.folder_id:
        await owned_folder(db, user.id, body.folder_id)
    taken = set((await db.scalars(select(StoredFile.name).where(
        StoredFile.user_id == user.id, StoredFile.folder_id.is_(None) if body.folder_id is None
        else StoredFile.folder_id == body.folder_id))).all())
    try:
        made = await store.save(db, user.id, _free_name(f.name, taken), store.read(f),
                                "upload", f.media_type)
    except store.QuotaExceeded as e:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "storage full") from e
    made.folder_id = body.folder_id
    await db.commit()
    return file_out(made)
