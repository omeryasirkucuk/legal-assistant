"""Chats: list, create, rename, delete, read messages, search history, and ask (streamed)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from legal_api import llm
from legal_api.agent.answer import answer_events
from legal_api.agent.detail import detail_stream
from legal_api.auth import DB, CurrentUser
from legal_api.chat.service import history, save_answer, spent_today, title_from
from legal_api.config import get_settings
from legal_api.db.app_models import Chat, LLMConnectionSettings, Message, MessageEvidence
from legal_api.db.session import get_sessionmaker
from legal_api.privacy.llm_settings import runtime_config

router = APIRouter(prefix="/chats", tags=["chats"])
logger = logging.getLogger(__name__)


class ChatOut(BaseModel):
    id: str
    title: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    meta: dict
    evidence: list[dict]
    created_at: str


class Ask(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _chat_out(chat: Chat) -> ChatOut:
    return ChatOut(id=str(chat.id), title=chat.title, updated_at=chat.updated_at.isoformat())


async def _owned_chat(db, user, chat_id: uuid.UUID) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return chat


@router.get("")
async def list_chats(user: CurrentUser, db: DB) -> list[ChatOut]:
    chats = await db.scalars(select(Chat).where(Chat.user_id == user.id)
                             .order_by(Chat.updated_at.desc()).limit(200))
    return [_chat_out(c) for c in chats]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_chat(body: Ask, user: CurrentUser, db: DB) -> ChatOut:
    chat = Chat(user_id=user.id, title=title_from(body.content))
    db.add(chat)
    await db.commit()
    return _chat_out(chat)


@router.patch("/{chat_id}")
async def rename_chat(chat_id: uuid.UUID, body: Rename, user: CurrentUser, db: DB) -> ChatOut:
    chat = await _owned_chat(db, user, chat_id)
    chat.title = body.title.strip()
    await db.commit()
    return _chat_out(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await db.delete(await _owned_chat(db, user, chat_id))
    await db.commit()


@router.get("/search")
async def search_history(q: str, user: CurrentUser, db: DB) -> list[dict]:
    """Full-text search over the user's past questions and answers."""
    query = func.websearch_to_tsquery("turkish", q)
    rows = await db.execute(
        select(Chat.id, Chat.title,
               func.ts_headline("turkish", Message.content, query,
                                "MaxWords=24, MinWords=8, StartSel=<<, StopSel=>>"))
        .join(Message, Message.chat_id == Chat.id)
        .where(Chat.user_id == user.id, Message.tsv.op("@@")(query))
        .order_by(func.ts_rank(Message.tsv, query).desc()).limit(30))
    seen: dict[str, dict] = {}
    for chat_id, title, snippet in rows:
        seen.setdefault(str(chat_id), {"chat_id": str(chat_id), "title": title,
                                       "snippet": snippet})
    return list(seen.values())


@router.get("/{chat_id}/messages")
async def list_messages(chat_id: uuid.UUID, user: CurrentUser, db: DB) -> list[MessageOut]:
    chat = await _owned_chat(db, user, chat_id)
    messages = (await db.scalars(select(Message).where(Message.chat_id == chat.id)
                                 .order_by(Message.created_at))).all()
    evidence = await db.execute(
        select(MessageEvidence.message_id, MessageEvidence.key, MessageEvidence.kind,
               MessageEvidence.citation, MessageEvidence.url)
        .where(MessageEvidence.message_id.in_([m.id for m in messages])))
    by_message: dict[uuid.UUID, list[dict]] = {}
    for message_id, key, kind, citation, url in evidence:
        by_message.setdefault(message_id, []).append(
            {"key": key, "kind": kind, "citation": citation, "url": url})
    return [MessageOut(id=str(m.id), role=m.role, content=m.content, meta=m.meta or {},
                       evidence=by_message.get(m.id, []), created_at=m.created_at.isoformat())
            for m in messages]


@router.get("/{chat_id}/messages/{message_id}/evidence/{key}")
async def evidence_text(chat_id: uuid.UUID, message_id: uuid.UUID, key: str,
                        user: CurrentUser, db: DB) -> dict:
    chat = await _owned_chat(db, user, chat_id)
    row = await db.scalar(select(MessageEvidence).join(Message)
                          .where(Message.chat_id == chat.id, MessageEvidence.message_id ==
                                 message_id, MessageEvidence.key == key))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return {"key": row.key, "kind": row.kind, "citation": row.citation, "url": row.url,
            "text": row.text, "fetched_at": row.fetched_at.isoformat()}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _guard_budget(db, user) -> None:
    if await spent_today(db, user.id) >= get_settings().daily_user_budget_usd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "daily budget reached")


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(events, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{chat_id}/messages")
async def ask(chat_id: uuid.UUID, body: Ask, user: CurrentUser, db: DB) -> StreamingResponse:
    """Stores the question and streams the grounded answer as server-sent events."""
    chat = await _owned_chat(db, user, chat_id)
    await _guard_budget(db, user)
    turns = await history(db, chat)
    question = Message(chat_id=chat.id, role="user", content=body.content.strip(), meta={})
    db.add(question)
    await db.commit()
    question_id = str(question.id)
    llm_config = runtime_config(await db.get(LLMConnectionSettings, 1))

    async def events() -> AsyncIterator[str]:
        token = llm.set_runtime_config(llm_config)
        try:
            yield _sse("question", {"id": question_id})
            holder: dict = {}
            async for event in answer_events(body.content.strip(), turns, holder):
                yield _sse(event.type, event.data)
            # The request-scoped session is closed once streaming starts; use a fresh one.
            async with get_sessionmaker()() as session:
                stored_chat = await session.get(Chat, chat.id)
                saved = await save_answer(session, stored_chat, holder["result"])
            yield _sse("saved", {"id": str(saved.id)})
        except Exception:
            # Tell the client the answer failed instead of cutting the stream silently.
            logger.exception("answer stream failed for chat %s", chat.id)
            yield _sse("error", {})
        finally:
            llm.reset_runtime_config(token)

    return _stream(events())


@router.post("/{chat_id}/messages/{message_id}/detail")
async def detail(chat_id: uuid.UUID, message_id: uuid.UUID, user: CurrentUser,
                 db: DB) -> StreamingResponse:
    """Streams (or replays) the detail section of an answer, written from its sources."""
    chat = await _owned_chat(db, user, chat_id)
    msg = await db.get(Message, message_id)
    if not msg or msg.chat_id != chat.id or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if "detail" in (msg.meta or {}):
        cached = msg.meta["detail"]

        async def replay() -> AsyncIterator[str]:
            yield _sse("detail", {"segments": cached})
        return _stream(replay())

    await _guard_budget(db, user)
    question = await db.scalar(select(Message.content).where(
        Message.chat_id == chat.id, Message.role == "user",
        Message.created_at < msg.created_at).order_by(Message.created_at.desc()).limit(1))
    rows = (await db.execute(select(MessageEvidence.key, MessageEvidence.citation,
                                    MessageEvidence.text)
                             .where(MessageEvidence.message_id == msg.id))).all()
    cited = {k for b in msg.meta.get("answer", {}).get("branches", []) for a in b["atoms"]
             for s in a["segments"] for k in s["keys"]}
    # Sources the short answer cited come first; the rest follow in retrieval order.
    sources = sorted(((k, c, t) for k, c, t in rows), key=lambda r: (r[0] not in cited,
                                                                     int(r[0][1:])))
    message_pk = msg.id
    llm_config = runtime_config(await db.get(LLMConnectionSettings, 1))

    async def events() -> AsyncIterator[str]:
        token = llm.set_runtime_config(llm_config)
        try:
            usage = llm.Usage()
            segments = []
            try:
                async for item in detail_stream(question or "", msg.content, sources, usage):
                    if isinstance(item, str):
                        yield _sse("delta", {"text": item})
                    else:
                        segments = [{"text": s.text, "keys": list(s.keys)} for s in item]
            except Exception:
                logger.exception("detail stream failed for message %s", message_pk)
                yield _sse("error", {})
                return
            async with get_sessionmaker()() as session:
                stored = await session.get(Message, message_pk)
                stored.meta = {**stored.meta, "detail": segments,
                               "detail_cost_usd": round(usage.cost_usd, 4)}
                await session.commit()
            yield _sse("detail", {"segments": segments})
        finally:
            llm.reset_runtime_config(token)

    return _stream(events())
