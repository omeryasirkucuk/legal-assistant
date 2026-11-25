"""Each user's file space: attachments they add and files made for them, within a quota.

Files live on disk under the storage directory, the protected payloads under opaque paths. The
`stored_files` table holds their names, sizes, links to chats, messages and drafts, and the
text read from them. Chats themselves do not count toward the quota.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.config import get_settings
from legal_api.db.file_models import StoredFile
from legal_api.files.extract import readable_text
from legal_api.files.labels import labels
from legal_api.privacy.file_crypto import FileProtectionError, document_key, seal, unseal

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
INLINE_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")


class QuotaExceeded(RuntimeError):
    pass


class FileTooLarge(RuntimeError):
    pass


def _root() -> Path:
    return get_settings().storage_dir


def sealed_path(user_id: uuid.UUID, file_id: uuid.UUID) -> Path:
    return Path("sealed") / str(user_id) / str(file_id) / "payload"


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def safe_name(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", name).strip(" .") or "file"
    return name[:200]


def media_type_of(name: str, given: str | None = None) -> str:
    if given and given != "application/octet-stream":
        return given
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def inline_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def used_bytes(db: AsyncSession, user_id: uuid.UUID) -> int:
    total = await db.scalar(select(func.coalesce(func.sum(StoredFile.size), 0))
                            .where(StoredFile.user_id == user_id))
    return int(total or 0)


async def save(db: AsyncSession, user_id: uuid.UUID, name: str, data: bytes, origin: str,
               media_type: str | None = None, chat_id: uuid.UUID | None = None,
               draft_id: uuid.UUID | None = None,
               petition_type: str | None = None,
               matter_id: uuid.UUID | None = None, *, commit: bool = True) -> StoredFile:
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLarge(name)
    if await used_bytes(db, user_id) + len(data) > get_settings().user_storage_bytes:
        raise QuotaExceeded(name)
    name = safe_name(name)
    file_id = uuid.uuid4()
    settings = get_settings()
    encrypted = bool(settings.document_encryption_key or settings.protected_data)
    if encrypted:
        payload = seal(data, document_key(settings.document_encryption_key), user_id, file_id)
        rel = sealed_path(user_id, file_id)
    else:
        payload = data
        rel = Path("users") / str(user_id) / str(file_id) / name
    text = readable_text(name, data)[:MAX_TEXT_CHARS]
    kind, area = labels(name, text, petition_type)
    stored = StoredFile(id=file_id, user_id=user_id, chat_id=chat_id, draft_id=draft_id,
                        matter_id=matter_id,
                        origin=origin, name=name, media_type=media_type_of(name, media_type),
                        size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        path=rel.as_posix(), encrypted=encrypted, text=text, kind=kind, area=area,
                        created_at=datetime.now(UTC))
    _write(_root() / rel, payload)
    db.add(stored)
    if not commit:
        return stored
    try:
        await db.commit()
    except Exception:
        remove_from_disk(stored)
        raise
    return stored


def read(stored: StoredFile) -> bytes:
    settings = get_settings()
    if not stored.encrypted and settings.protected_data:
        raise FileProtectionError("legacy file has not been encrypted")
    payload = (_root() / stored.path).read_bytes()
    if not stored.encrypted:
        return payload
    return unseal(payload, document_key(settings.document_encryption_key), stored.user_id, stored.id)


async def encrypt_existing(db: AsyncSession, *, file_ids: list[uuid.UUID] | None = None) -> int:
    """Move old files to the sealed store with the API offline. Safe to resume after a stop."""
    key = document_key(get_settings().document_encryption_key)
    query = select(StoredFile.id)
    if file_ids is not None:
        query = query.where(StoredFile.id.in_(file_ids))
    ids = (await db.scalars(query)).all()
    converted = 0
    for file_id in ids:
        stored = await db.get(StoredFile, file_id, with_for_update=True)
        if stored is None:
            continue
        target = sealed_path(stored.user_id, file_id)
        if stored.encrypted:
            payload = unseal((_root() / stored.path).read_bytes(), key, stored.user_id, file_id)
        else:
            payload = (_root() / stored.path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != stored.sha256:
            raise FileProtectionError(f"checksum mismatch for file {file_id}")
        if not stored.encrypted:
            _write(_root() / target, seal(payload, key, stored.user_id, file_id))
            stored.path = target.as_posix()
            stored.encrypted = True
            converted += 1
        legacy_directory = _root() / "users" / str(stored.user_id) / str(file_id)
        await db.commit()
        if legacy_directory.exists():
            shutil.rmtree(legacy_directory)
    return converted


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
