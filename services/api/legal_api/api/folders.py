"""Folders in My files: make, rename, move and delete them. Deleting a folder keeps what was
in it: its files and folders move up to the folder that held it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from legal_api.auth import DB, CurrentUser
from legal_api.db.file_models import FileFolder, StoredFile

router = APIRouter(prefix="/folders", tags=["files"])


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None


class FolderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: uuid.UUID | None = None
    to_top: bool = False          # move to the top level (parent_id null means "unchanged")


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None
    created_at: datetime


def _out(f: FileFolder) -> FolderOut:
    return FolderOut(id=str(f.id), name=f.name,
                     parent_id=str(f.parent_id) if f.parent_id else None, created_at=f.created_at)


async def owned_folder(db, user_id: uuid.UUID, folder_id: uuid.UUID) -> FileFolder:
    f = await db.get(FileFolder, folder_id)
    if f is None or f.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "folder not found")
    return f


async def _ancestors(db, folder: FileFolder) -> set[uuid.UUID]:
    seen, at = set(), folder
    while at is not None and at.id not in seen:
        seen.add(at.id)
        at = await db.get(FileFolder, at.parent_id) if at.parent_id else None
    return seen


@router.get("")
async def list_folders(user: CurrentUser, db: DB) -> list[FolderOut]:
    rows = (await db.scalars(select(FileFolder).where(FileFolder.user_id == user.id)
                             .order_by(FileFolder.name))).all()
    return [_out(f) for f in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(body: FolderIn, user: CurrentUser, db: DB) -> FolderOut:
    if body.parent_id:
        await owned_folder(db, user.id, body.parent_id)
    f = FileFolder(user_id=user.id, parent_id=body.parent_id, name=body.name.strip(),
                   created_at=datetime.now(UTC))
    db.add(f)
    await db.commit()
    return _out(f)


@router.patch("/{folder_id}")
async def edit_folder(folder_id: uuid.UUID, body: FolderPatch, user: CurrentUser, db: DB
                      ) -> FolderOut:
    f = await owned_folder(db, user.id, folder_id)
    if body.name is not None:
        f.name = body.name.strip()
    if body.to_top:
        f.parent_id = None
    elif body.parent_id is not None:
        target = await owned_folder(db, user.id, body.parent_id)
        if f.id in await _ancestors(db, target):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a folder cannot go inside itself")
        f.parent_id = target.id
    await db.commit()
    return _out(f)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    f = await owned_folder(db, user.id, folder_id)
    await db.execute(update(StoredFile).where(StoredFile.folder_id == f.id)
                     .values(folder_id=f.parent_id))
    await db.execute(update(FileFolder).where(FileFolder.parent_id == f.id)
                     .values(parent_id=f.parent_id))
    await db.delete(f)
    await db.commit()
