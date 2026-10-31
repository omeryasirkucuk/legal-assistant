"""Each user's file space: attachments they add and files made for them, within a quota.

Files live on disk under the storage directory (users/<user id>/<file id>/<name>); the
`stored_files` table holds their names, sizes, links to chats, messages and drafts, and the
text read from them. Chats themselves do not count toward the quota.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.config import get_settings
from legal_api.db.file_models import StoredFile
from legal_api.files.extract import readable_text
from legal_api.files.labels import labels

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 200_000


class QuotaExceeded(RuntimeError):
    pass


class FileTooLarge(RuntimeError):
    pass


def _root() -> Path:
    return get_settings().storage_dir


def safe_name(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", name).strip(" .") or "file"
    return name[:200]


def media_type_of(name: str, given: str | None = None) -> str:
    if given and given != "application/octet-stream":
        return given
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


async def used_bytes(db: AsyncSession, user_id: uuid.UUID) -> int:
    total = await db.scalar(select(func.coalesce(func.sum(StoredFile.size), 0))
                            .where(StoredFile.user_id == user_id))
    return int(total or 0)


async def save(db: AsyncSession, user_id: uuid.UUID, name: str, data: bytes, origin: str,
               media_type: str | None = None, chat_id: uuid.UUID | None = None,
               draft_id: uuid.UUID | None = None,
               petition_type: str | None = None,
               matter_id: uuid.UUID | None = None) -> StoredFile:
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLarge(name)
    if await used_bytes(db, user_id) + len(data) > get_settings().user_storage_bytes:
        raise QuotaExceeded(name)
    name = safe_name(name)
    file_id = uuid.uuid4()
    rel = Path("users") / str(user_id) / str(file_id) / name
    path = _root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    text = readable_text(name, data)[:MAX_TEXT_CHARS]
    kind, area = labels(name, text, petition_type)
    stored = StoredFile(id=file_id, user_id=user_id, chat_id=chat_id, draft_id=draft_id,
                        matter_id=matter_id,
                        origin=origin, name=name, media_type=media_type_of(name, media_type),
                        size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        path=rel.as_posix(), text=text, kind=kind, area=area,
                        created_at=datetime.now(UTC))
    db.add(stored)
    await db.commit()
    return stored


def read(stored: StoredFile) -> bytes:
    return (_root() / stored.path).read_bytes()


def remove_from_disk(stored: StoredFile) -> None:
    shutil.rmtree((_root() / stored.path).parent, ignore_errors=True)


async def delete(db: AsyncSession, stored: StoredFile) -> None:
    remove_from_disk(stored)
    await db.delete(stored)
    await db.commit()


async def owned(db: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID]) -> list[StoredFile]:
    if not ids:
        return []
    rows = (await db.scalars(select(StoredFile).where(StoredFile.id.in_(ids),
                                                      StoredFile.user_id == user_id))).all()
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda f: order[f.id])
