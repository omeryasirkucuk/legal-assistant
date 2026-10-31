"""Search over the lawyer's case files as they type: a file matches when every typed term is
in its details (client, subject, other side, court, case number, notes), and a document
matches when every term is in its name or text. Matching is the chat search's: Turkish
casefold, partial words count."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.chat.history_search import folded, search_terms, snippet
from legal_api.db.app_models import Chat
from legal_api.db.file_models import StoredFile
from legal_api.db.matter_models import Matter

MAX_MATTERS = 10
MAX_DOCUMENTS = 15
_FIELDS = ("client", "subject", "opponent", "court", "case_no", "notes")


def _matter_text():
    return func.concat_ws(" ", *(getattr(Matter, f) for f in _FIELDS))


def _all_in(column, terms: list[str]):
    return and_(*(folded(column).like(f"%{t}%") for t in terms))


async def search_matters(db: AsyncSession, user_id: uuid.UUID, q: str) -> dict:
    terms = search_terms(q)
    if not terms:
        return {"matters": [], "documents": []}
    matters = (await db.scalars(
        select(Matter).where(Matter.user_id == user_id, _all_in(_matter_text(), terms))
        .order_by(Matter.closed, Matter.updated_at.desc()).limit(MAX_MATTERS))).all()

    # A document is in a file when added to it or attached in one of its chats.
    in_matter = func.coalesce(StoredFile.matter_id, Chat.matter_id)
    doc_text = func.concat_ws(" ", StoredFile.name, StoredFile.text)
    rows = (await db.execute(
        select(StoredFile.id, StoredFile.name, StoredFile.text, Matter.id, Matter.client)
        .outerjoin(Chat, Chat.id == StoredFile.chat_id)
        .join(Matter, Matter.id == in_matter)
        .where(StoredFile.user_id == user_id, Matter.user_id == user_id,
               or_(_all_in(StoredFile.name, terms), _all_in(doc_text, terms)))
        .order_by(StoredFile.created_at.desc()).limit(MAX_DOCUMENTS))).all()

    def matter_snippet(m: Matter) -> str:
        return snippet(" · ".join(v for f in _FIELDS if (v := getattr(m, f))), terms)

    return {
        "matters": [{"matter_id": str(m.id), "client": m.client, "subject": m.subject,
                     "closed": m.closed, "snippet": matter_snippet(m)} for m in matters],
        "documents": [{"file_id": str(fid), "name": name, "matter_id": str(mid), "client": client,
                       "snippet": snippet(text or name, terms)}
                      for fid, name, text, mid, client in rows],
    }
