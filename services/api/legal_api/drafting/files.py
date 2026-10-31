"""A draft's files in the user's space: the petition in its format, and other formats when
the lawyer downloads them. They are made again when the draft's text changes."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.db.drafting_models import Draft
from legal_api.db.file_models import StoredFile
from legal_api.drafting.export import MEDIA_TYPES, render
from legal_api.drafting.rich import file_blocks
from legal_api.files import store


def file_name(title: str, fmt: str) -> str:
    """The chat's title as a file name: the lawyer recognises the file in their downloads."""
    base = store.safe_name(title).rsplit(".", 1)[0] if title else "petition"
    return f"{' '.join(base.split())[:80] or 'petition'}.{fmt}"


async def draft_file(db: AsyncSession, draft: Draft, fmt: str) -> StoredFile:
    """The stored file of the draft in `fmt`, made now if there is none."""
    found = await db.scalar(select(StoredFile).where(
        StoredFile.draft_id == draft.id, StoredFile.name == file_name(draft.title, fmt)))
    if found is not None:
        return found
    return await store.save(db, draft.user_id, file_name(draft.title, fmt),
                            render(file_blocks(draft), fmt, draft.title), "generated", MEDIA_TYPES[fmt],
                            chat_id=draft.chat_id, draft_id=draft.id,
                            petition_type=draft.petition_type)


async def refresh_draft_file(db: AsyncSession, draft: Draft) -> StoredFile:
    """Drop the draft's files (its text changed) and make the one in its format."""
    rows = (await db.scalars(select(StoredFile).where(StoredFile.draft_id == draft.id))).all()
    for f in rows:
        store.remove_from_disk(f)
    await db.execute(delete(StoredFile).where(StoredFile.draft_id == draft.id))
    await db.commit()
    return await draft_file(db, draft, draft.meta.get("format", "docx"))
