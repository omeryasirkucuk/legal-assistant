"""Case files: their contents gathered in one place, and what every answer in one knows."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.db.app_models import Chat
from legal_api.db.drafting_models import Draft
from legal_api.db.file_models import StoredFile
from legal_api.db.matter_models import Matter, MatterDeadline
from legal_api.files.context import Attachment
from legal_api.locale import matter_terms


async def owned(db: AsyncSession, user_id: uuid.UUID, matter_id: uuid.UUID) -> Matter | None:
    matter = await db.get(Matter, matter_id)
    return matter if matter is not None and matter.user_id == user_id else None


async def chats_of(db: AsyncSession, matter_id: uuid.UUID) -> list[Chat]:
    return list((await db.scalars(select(Chat).where(Chat.matter_id == matter_id)
                                  .order_by(Chat.updated_at.desc()))).all())


async def files_of(db: AsyncSession, matter_id: uuid.UUID) -> list[StoredFile]:
    """Documents added to the matter and files of its chats (attachments, petitions)."""
    chat_ids = select(Chat.id).where(Chat.matter_id == matter_id)
    return list((await db.scalars(select(StoredFile).where(or_(
        StoredFile.matter_id == matter_id, StoredFile.chat_id.in_(chat_ids)))
        .order_by(StoredFile.created_at.desc()))).all())


async def drafts_of(db: AsyncSession, matter_id: uuid.UUID) -> list[Draft]:
    chat_ids = select(Chat.id).where(Chat.matter_id == matter_id)
    return list((await db.scalars(select(Draft).where(Draft.chat_id.in_(chat_ids))
                                  .order_by(Draft.updated_at.desc()))).all())


async def deadlines_of(db: AsyncSession, matter_ids: list[uuid.UUID]) -> list[MatterDeadline]:
    if not matter_ids:
        return []
    return list((await db.scalars(select(MatterDeadline).where(
        MatterDeadline.matter_id.in_(matter_ids)).order_by(MatterDeadline.due))).all())


def context(matter: Matter, files: list[StoredFile]) -> Attachment:
    """The matter as material for an answer in it: parties, court, the lawyer's notes, and
    the names of its documents, so the lawyer need not tell the case again in every chat."""
    t = matter_terms()
    lines = [t["context_title"].format(client=matter.client)]
    for key in ("subject", "opponent", "court", "case_no"):
        value = getattr(matter, key)
        if value:
            lines.append(f"{t['fields'][key]}: {value}")
    if matter.notes.strip():
        lines += ["", t["fields"]["notes"] + ":", matter.notes.strip()]
    if files:
        lines += ["", t["documents"] + ": " + ", ".join(f.name for f in files[:30])]
    return Attachment(t["context_name"].format(client=matter.client), "text/plain", "\n".join(lines))
