"""Chat persistence: conversation history for the model and storing finished answers."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.agent.turn import EvidenceCopy, Previous
from legal_api.config import get_settings
from legal_api.db.app_models import Chat, LlmSpend, Message, MessageEvidence
from legal_api.files import store as file_store
from legal_api.workspace.documents import WORD_MEDIA_TYPE
from legal_api.workspace.session import Context

HISTORY_TURNS = 6
TITLE_CHARS = 60
# Citation markers and section tags are not conversation; strip them for history.
_LEGACY_MARKUP = re.compile(r"\[\[E\d+\]\]|</?(?:short|detail|quote[^>]*)>")
_SHORT = re.compile(r"<short>([\s\S]*?)</short>")


def _as_history(content: str) -> str:
    """An answer enters history as its short answer: what the lawyer read."""
    short = _SHORT.search(content)
    return _LEGACY_MARKUP.sub("", short.group(1) if short else content).strip()


def title_from(question: str) -> str:
    line = " ".join(question.split())
    return line if len(line) <= TITLE_CHARS else line[:TITLE_CHARS - 1].rstrip() + "…"


async def history(db: AsyncSession, chat: Chat) -> list[dict]:
    """Earlier turns as plain text: what was said, without the sources. The model sees the
    conversation but must retrieve sources again before relying on anything in it."""
    rows = (await db.scalars(select(Message).where(Message.chat_id == chat.id)
                             .order_by(Message.created_at.desc())
                             .limit(HISTORY_TURNS * 2))).all()
    # Skip direct exchanges and stop at the question that began the current topic.
    selected = []
    skip_question = False
    stop_after_question = False
    for row in rows:
        if row.role == "assistant":
            meta = row.meta or {}
            skip_question = (meta.get("answer") or {}).get("task") == "direct"
            stop_after_question = (meta.get("trace") or {}).get("starts_topic", False)
        if not skip_question:
            selected.append(row)
        if row.role == "user":
            if stop_after_question:
                break
            skip_question = False
    turns = [{"role": m.role, "content": _as_history(m.content)}
             for m in reversed(selected) if m.content.strip()]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


async def drop_unanswered(db: AsyncSession, chat: Chat) -> None:
    """Remove a last question that has no answer. It is left behind when an answer failed or
    the API restarted while answering (runs live in process memory); kept, it would reach the
    model as a second user turn in a row and stay in the chat with no answer under it."""
    last = await db.scalar(select(Message).where(Message.chat_id == chat.id)
                           .order_by(Message.created_at.desc()).limit(1))
    if last is not None and last.role == "user":
        await db.delete(last)
        await db.commit()


async def previous_turn(db: AsyncSession, chat: Chat) -> Previous | None:
    """The chat's last answer, the question it answered and its sources."""
    answer = await db.scalar(select(Message).where(Message.chat_id == chat.id,
                                                   Message.role == "assistant",
                                                   Message.meta["answer"]["task"].astext
                                                   .is_distinct_from("direct"))
                             .order_by(Message.created_at.desc()).limit(1))
    if answer is None:
        return None
    question = await db.scalar(select(Message).where(
        Message.chat_id == chat.id, Message.role == "user",
        Message.created_at < answer.created_at).order_by(Message.created_at.desc()).limit(1))
    evidence = (await db.scalars(select(MessageEvidence)
                                 .where(MessageEvidence.message_id == answer.id))).all()
    structure = dict((answer.meta or {}).get("answer") or {})
    if question and "case_file_ids" not in structure:
        structure["case_file_ids"] = [f["id"] for f in (question.meta or {}).get("attachments", [])
                                      if f.get("id")]
    return Previous(question.content if question else "", structure,
                    _as_history(answer.content),
                    [EvidenceCopy(e.key, e.kind, e.citation, e.url, e.text, e.fetched_at)
                     for e in evidence])



async def workspace_context(db: AsyncSession, chat: Chat, files: list) -> Context:
    """Find the latest durable plan even if another kind of answer intervened."""
    row = (await db.execute(select(Message.id, Message.meta["workspace"]).where(
        Message.chat_id == chat.id, Message.role == "assistant",
        Message.meta["workspace"]["plan"].astext.is_not(None))
        .order_by(Message.created_at.desc()).limit(1))).first()
    context = Context(files)
    if row:
        context.previous = row[1]
        context.previous_evidence = list(await db.scalars(
            select(MessageEvidence).where(MessageEvidence.message_id == row.id,
                                         MessageEvidence.kind != "calculation")
            .order_by(MessageEvidence.key)))
    return context


async def save_answer(db: AsyncSession, chat: Chat, result) -> Message:
    """`result`: a pipeline WrittenResult (or the legacy AnswerResult): text, structure(),
    usage, timings, trace, ledger of sources, optionally checked."""
    msg = Message(chat_id=chat.id, role="assistant", content=result.text, meta={
        "answer": result.structure(),
        "cost_usd": round(result.usage.cost_usd, 4),
        "timings": result.timings,
        "trace": result.trace,
        **({"workspace": result.workspace} if getattr(result, "workspace", None) else {}),
        **({"checked": result.checked} if getattr(result, "checked", None) else {}),
    })
    db.add(msg)
    written_files = []
    try:
        await db.flush()
        db.add_all(MessageEvidence(message_id=msg.id, key=e.key, kind=e.kind, citation=e.citation,
                                   url=e.url, text=e.text, fetched_at=e.fetched_at)
                   for e in result.ledger)
        workspace = getattr(result, "workspace", None)
        copies = getattr(result, "workspace_files", [])
        if workspace and copies:
            updated = []
            for edit, data in zip(workspace["edits"], copies, strict=True):
                filename = f"{Path(edit['name']).stem[:190]}-hesap-v{workspace['revision']}.docx"
                stored = await file_store.save(db, chat.user_id, filename, data, "generated",
                                               WORD_MEDIA_TYPE, chat_id=chat.id, commit=False)
                written_files.append(stored)
                stored.message_id = msg.id
                updated.append({**edit, "file_id": str(stored.id)})
            msg.meta = {**msg.meta, "workspace": {**workspace, "edits": updated}}
        chat.updated_at = datetime.now(UTC)
        await db.commit()
    except BaseException:
        for file in written_files:
            file_store.remove_from_disk(file)
        raise
    return msg


async def spent_today(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Recorded model spend since 00:00 UTC, independent of chat retention."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total = await db.scalar(select(func.coalesce(func.sum(LlmSpend.cost_usd), 0.0))
                            .where(LlmSpend.user_id == user_id, LlmSpend.created_at >= start))
    return float(total or 0.0)


def message_cost():
    """An assistant message's LLM spend: the answer and, if opened, its detail section."""
    return (func.coalesce(cast(Message.meta["cost_usd"].astext, Float), 0.0)
            + func.coalesce(cast(Message.meta["detail_cost_usd"].astext, Float), 0.0))


async def chat_costs(db: AsyncSession, chat_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    rows = await db.execute(
        select(Message.chat_id, func.sum(message_cost()))
        .where(Message.chat_id.in_(chat_ids), Message.role == "assistant")
        .group_by(Message.chat_id))
    return {chat_id: round(float(total or 0), 4) for chat_id, total in rows}


async def today_stats(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """The user's answers since 00:00 UTC: how many, how long they took, what they cost."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = cast(Message.meta["timings"]["total_s"].astext, Float)
    count, average, longest = (await db.execute(
        select(func.count(), func.avg(seconds), func.max(seconds))
        .join(Chat, Chat.id == Message.chat_id)
        .where(Chat.user_id == user_id, Message.role == "assistant",
               Message.created_at >= start))).one()
    return {"answers": int(count or 0), "average_s": round(float(average or 0), 1),
            "longest_s": round(float(longest or 0), 1),
            # The meter shows what the budget counts: answers and everything else.
            "cost_usd": round(await spent_today(db, user_id), 4),
            "budget_usd": get_settings().daily_user_budget_usd}
