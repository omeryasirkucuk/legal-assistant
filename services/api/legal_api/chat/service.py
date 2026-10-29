"""Chat persistence: conversation history for the model and storing finished answers."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.agent.answer import AnswerResult
from legal_api.db.app_models import Chat, Message, MessageEvidence

HISTORY_TURNS = 6
TITLE_CHARS = 60
# Answers stored before the citations API carried inline markup; strip it for history.
_LEGACY_MARKUP = re.compile(r"\[\[E\d+\]\]|</?(?:short|detail|quote[^>]*)>")


def title_from(question: str) -> str:
    line = " ".join(question.split())
    return line if len(line) <= TITLE_CHARS else line[:TITLE_CHARS - 1].rstrip() + "…"


async def history(db: AsyncSession, chat: Chat) -> list[dict]:
    """Earlier turns as plain text: what was said, without the sources. The model sees the
    conversation but must retrieve sources again before relying on anything in it."""
    rows = (await db.scalars(select(Message).where(Message.chat_id == chat.id)
                             .order_by(Message.created_at.desc())
                             .limit(HISTORY_TURNS * 2))).all()[::-1]
    turns = [{"role": m.role, "content": _LEGACY_MARKUP.sub("", m.content).strip()}
             for m in rows if m.content.strip()]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


async def save_answer(db: AsyncSession, chat: Chat, result: AnswerResult) -> Message:
    msg = Message(chat_id=chat.id, role="assistant", content=result.text, meta={
        "answer": result.structure(),
        "cost_usd": round(result.usage.cost_usd, 4),
        "timings": result.timings,
    })
    db.add(msg)
    await db.flush()
    db.add_all(MessageEvidence(message_id=msg.id, key=e.key, kind=e.kind, citation=e.citation,
                               url=e.url, text=e.text, fetched_at=e.fetched_at)
               for e in result.ledger)
    chat.updated_at = datetime.now(UTC)
    await db.commit()
    return msg


async def spent_today(db: AsyncSession, user_id: uuid.UUID) -> float:
    """LLM spend of the user's answers (and their detail sections) since 00:00 UTC."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total = await db.scalar(
        select(func.coalesce(func.sum(
            cast(Message.meta["cost_usd"].astext, Float)
            + func.coalesce(cast(Message.meta["detail_cost_usd"].astext, Float), 0.0)), 0.0))
        .join(Chat, Chat.id == Message.chat_id)
        .where(Chat.user_id == user_id, Message.role == "assistant",
               Message.created_at >= start))
    return float(total or 0.0)
