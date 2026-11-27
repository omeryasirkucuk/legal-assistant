"""Chats: list, create, rename, delete, read messages, search history, and ask (streamed)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from legal_api import llm
from legal_api.agent.detail import detail_stream
from legal_api.agent.power import POWERS, power_of
from legal_api.agent.route import direct_intent
from legal_api.agent.turn import turn_events
from legal_api.auth import DB, CurrentUser
from legal_api.chat import runs
from legal_api.chat.history_search import search_chats
from legal_api.chat.service import (
    chat_costs,
    drop_unanswered,
    history,
    previous_turn,
    save_answer,
    title_from,
    today_stats,
    workspace_context,
)
from legal_api.chat.titles import generate_title
from legal_api.db.app_models import Chat, LLMConnectionSettings, Message, MessageEvidence
from legal_api.db.file_models import StoredFile
from legal_api.db.session import get_sessionmaker
from legal_api.drafting.files import refresh_draft_file
from legal_api.drafting.store import file_format, record_reply, save_draft, style_book
from legal_api.files.context import Attachment
from legal_api.files.store import owned as owned_files
from legal_api.files.store import read as read_file
from legal_api.matters.agenda import agenda as load_agenda
from legal_api.matters.documents import Document
from legal_api.matters.documents import material as matter_material
from legal_api.matters.service import context as matter_context
from legal_api.matters.service import files_of as matter_files
from legal_api.matters.service import owned as owned_matter
from legal_api.privacy.llm_settings import runtime_config
from legal_api.retrieval.statutes import article_request
from legal_api.spend import guard_budget, record_spend
from legal_api.workspace.documents import WORD_MEDIA_TYPE
from legal_api.workspace.workbook import MEDIA_TYPE as XLSX_TYPE
from legal_api.workspace.workbook import workbook

router = APIRouter(prefix="/chats", tags=["chats"])
logger = logging.getLogger(__name__)

ANSWER_TIMEOUT_S = 60
DEEP_ANSWER_TIMEOUT_S = 105


class ChatOut(BaseModel):
    id: str
    title: str
    updated_at: str
    cost_usd: float = 0.0     # LLM spend of all answers in the chat
    matter_id: str | None = None   # the case file it belongs to


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    meta: dict
    evidence: list[dict]
    created_at: str


class Ask(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    power: str | None = None        # fast | balanced | deep
    matter_id: uuid.UUID | None = None   # on creating a chat: the case file it is opened in


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _chat_out(chat: Chat, cost: float = 0.0) -> ChatOut:
    return ChatOut(id=str(chat.id), title=chat.title, updated_at=chat.updated_at.isoformat(),
                   cost_usd=cost, matter_id=str(chat.matter_id) if chat.matter_id else None)


async def _owned_chat(db, user, chat_id: uuid.UUID) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return chat


@router.get("")
async def list_chats(user: CurrentUser, db: DB) -> list[ChatOut]:
    chats = (await db.scalars(select(Chat).where(Chat.user_id == user.id)
                              .order_by(Chat.updated_at.desc()).limit(200))).all()
    costs = await chat_costs(db, [c.id for c in chats])
    return [_chat_out(c, costs.get(c.id, 0.0)) for c in chats]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_chat(body: Ask, user: CurrentUser, db: DB) -> ChatOut:
    matter = await owned_matter(db, user.id, body.matter_id) if body.matter_id else None
    chat = Chat(user_id=user.id, title=title_from(body.content),
                matter_id=matter.id if matter else None)
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
    """Search the user's chats by question, answer or title; partial words match."""
    return await search_chats(db, user.id, q)


@router.get("/response-models")
async def response_models(user: CurrentUser, db: DB) -> dict[str, str]:
    token = llm.set_runtime_config(runtime_config(await db.get(LLMConnectionSettings, 1)))
    try:
        return {
            name: llm.routed(power.write_role) or llm.model_for(power.write_role)
            for name, power in POWERS.items()
        }
    finally:
        llm.reset_runtime_config(token)


@router.get("/stats/today")
async def stats_today(user: CurrentUser, db: DB) -> dict:
    """Answers given today and how long they took, for the sidebar."""
    return await today_stats(db, user)


def _message_meta(metadata: dict) -> dict:
    snapshot = metadata.get("workspace")
    if not snapshot:
        return metadata
    return {**metadata, "workspace": {
        "revision": snapshot["revision"], "format": snapshot["format"],
        "pending": bool(snapshot.get("pending")), "changes": snapshot["changes"],
        "edits": [{"name": item["name"], "changes": item["changes"]}
                  for item in snapshot["edits"]],
    }}


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
    result = []
    direct_question = False
    for message in messages:
        meta = _message_meta(message.meta or {})
        sources = by_message.get(message.id, [])
        if message.role == "user":
            direct_question = not meta.get("attachments") and bool(direct_intent(message.content))
        elif message.role == "assistant":
            # Old small-talk replies may carry the writer's generic missing-citation flag.
            if direct_question and not sources:
                checked = meta.get("checked") or {}
                claims = checked.get("claims") or []
                if (not checked.get("issues") and len(claims) == 1
                        and claims[0].get("reason") == "citation_missing"
                        and not claims[0].get("sentence") and not claims[0].get("keys")):
                    meta = {key: value for key, value in meta.items() if key != "checked"}
            direct_question = False
        result.append(MessageOut(id=str(message.id), role=message.role, content=message.content,
                                 meta=meta, evidence=sources,
                                 created_at=message.created_at.isoformat()))
    return result


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



@router.get("/{chat_id}/messages/{message_id}/output/{output}")
async def workspace_output(chat_id: uuid.UUID, message_id: uuid.UUID, output: str,
                           user: CurrentUser, db: DB) -> Response:
    chat = await _owned_chat(db, user, chat_id)
    message = await db.scalar(select(Message).where(Message.id == message_id,
                                                    Message.chat_id == chat.id,
                                                    Message.role == "assistant"))
    snapshot = (message.meta or {}).get("workspace") if message else None
    if not snapshot:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        if output == "xlsx" and snapshot["format"] == "xlsx":
            payload = await asyncio.to_thread(workbook, snapshot)
            filename = f"Hesap-v{snapshot['revision']}.xlsx"
            kind = XLSX_TYPE
        elif output.isascii() and output.isdigit() and len(output) == 1:
            position = int(output)
            if position >= len(snapshot["edits"]):
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            edit = snapshot["edits"][position]
            file = await db.get(StoredFile, uuid.UUID(edit["file_id"]))
            if not file or file.user_id != user.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            payload = await asyncio.to_thread(read_file, file)
            filename = file.name
            kind = WORD_MEDIA_TYPE
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Çıktı bu kayıt üzerinden yeniden üretilemedi.") from exc
    return Response(payload, media_type=kind, headers={
        "Content-Disposition": f"attachment; filename=output; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _title_with_budget(text: str, usage: llm.Usage) -> str | None:
    try:
        async with asyncio.timeout(3):
            return await generate_title(text, usage)
    except TimeoutError:
        return None


def _finished_title(task: asyncio.Task | None) -> str | None:
    """The generated title, or None when there is none or it failed (the chat keeps its
    provisional title from the question)."""
    if task is None or not task.done() or task.cancelled():
        return None
    try:
        return task.result()
    except Exception as exc:  # noqa: BLE001 - a title failure cannot fail a completed answer
        logger.error("title generation failed (%s)", type(exc).__name__)
        return None


def _stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(events, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{chat_id}/messages")
async def ask(chat_id: uuid.UUID, body: Ask, user: CurrentUser, db: DB) -> StreamingResponse:
    """Stores the question, starts the answer as a server-side run, and streams the run's
    events. Closing the connection does not stop the answer; see GET /{chat_id}/run."""
    chat = await _owned_chat(db, user, chat_id)
    if runs.active(chat.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "an answer is already running")
    await guard_budget(db, user)
    await drop_unanswered(db, chat)   # no run is active, so it will never be answered
    turns = await history(db, chat)
    previous = await previous_turn(db, chat)
    text = body.content.strip()
    files = await owned_files(db, user.id, body.file_ids)
    is_direct = not files and direct_intent(text) is not None
    question = Message(chat_id=chat.id, role="user", content=text, meta={
        "attachments": [{"id": str(f.id), "name": f.name, "media_type": f.media_type,
                         "size": f.size} for f in files]} if files else {})
    db.add(question)
    await db.flush()
    for f in files:
        f.chat_id, f.message_id = chat.id, question.id
    await db.commit()
    attachments = [Attachment(f.name, f.media_type, f.text,
                              await asyncio.to_thread(read_file, f) if f.media_type.startswith("image/") else None)
                   for f in files]
    in_file = []
    # In a case file, its parties, court, notes and documents come with every question.
    matter = await owned_matter(db, user.id, chat.matter_id) if chat.matter_id else None
    if matter is not None:
        in_file = await matter_files(db, matter.id)
        if not is_direct:
            attached = {f.id for f in files}
            docs = [Document(f.id, f.name, f.text or "") for f in in_file
                    if f.id not in attached and not f.media_type.startswith("image/")]
            attachments[:0] = [matter_context(matter, in_file),
                               *await asyncio.to_thread(matter_material, text, docs)]
    # The recorded deadlines, cited only if the question turns out to be about them.
    agenda = await load_agenda(db, user.id, matter)
    chat_files = await db.scalars(select(StoredFile).where(
        StoredFile.user_id == user.id, or_(StoredFile.chat_id == chat.id,
                                         StoredFile.id.in_([f.id for f in in_file])))
        .order_by(StoredFile.created_at.desc(), StoredFile.id).limit(75))
    seen_files = {f.id: f for f in [*files, *chat_files]}
    context = await workspace_context(db, chat, list(seen_files.values()))
    power = power_of(body.power)
    question_id = str(question.id)
    llm_config = runtime_config(await db.get(LLMConnectionSettings, 1))
    chat_pk, user_pk = chat.id, user.id

    async def load_style():
        async with get_sessionmaker()() as session:
            return await style_book(session, user_pk, text)

    async def work(run: runs.Run) -> None:
        token = llm.set_runtime_config(llm_config)
        try:
            await answer_and_save(run)
        except asyncio.CancelledError:
            # Stopped by the lawyer: the question has no answer, so it leaves the chat too.
            async with get_sessionmaker()() as session:
                stored = await session.get(Message, uuid.UUID(question_id))
                if stored is not None:
                    await session.delete(stored)
                    await session.commit()
            raise
        finally:
            llm.reset_runtime_config(token)

    async def answer_and_save(run: runs.Run) -> None:
        started = time.monotonic()
        run.emit("question", {"id": question_id, "content": text,
                              "started_at": time.time() * 1000})
        holder: dict = {}
        usage = llm.Usage()
        # The first question names the chat; written alongside the answer.
        title_task = (asyncio.create_task(_title_with_budget(text, usage))
                      if previous is None and (files or not (is_direct or article_request(text)))
                      else None)
        first_delta = None
        try:
            events = turn_events(text, turns, previous, holder, power=power,
                                 attachments=attachments, agenda=agenda, usage=usage,
                                 workspace=context, style_loader=load_style)
            timeout = DEEP_ANSWER_TIMEOUT_S if power.name == "deep" else ANSWER_TIMEOUT_S
            async with asyncio.timeout(timeout), aclosing(events):
                async for event in events:
                    if event.type == "delta" and first_delta is None:
                        first_delta = round(time.monotonic() - started, 3)
                    if event.type == "final":
                        timings = event.data.setdefault("timings", {})
                        if first_delta is not None:
                            timings["first_delta_s"] = first_delta
                        timings["total_s"] = round(time.monotonic() - started, 3)
                    run.emit(event.type, event.data)
            title = _finished_title(title_task)
        finally:
            if title_task is not None:
                if not title_task.done():
                    title_task.cancel()
                await asyncio.gather(title_task, return_exceptions=True)
            async with get_sessionmaker()() as session:
                await record_spend(session, user_pk, "chat_answer", usage)
                await session.commit()
        async with get_sessionmaker()() as session:
            stored_chat = await session.get(Chat, chat_pk)
            if stored_chat is None:      # deleted while answering
                return
            if title:
                stored_chat.title = title
            result = holder["result"]
            saved = await save_answer(session, stored_chat, result)
            draft = None
            u = getattr(result, "understanding", None)
            asked = getattr(result, "asked", False)
            if u is not None and previous is not None and (previous.answer or {}).get("asked"):
                await record_reply(session, user_pk, skipped=u.write_now)
            fmt = await file_format(session, user_pk, u.output_format) if u and not asked else None
            if u is not None and u.task == "drafting" and not asked:
                draft = await save_draft(session, user_pk, chat_pk, saved.id, u.petition_type,
                                         title or stored_chat.title, result.full_text, fmt)
                await refresh_draft_file(session, draft)
        if draft is not None:
            run.emit("draft", {"id": str(draft.id), "format": fmt})
        if title:
            run.emit("title", {"chat_id": str(chat_pk), "title": title})
        run.emit("saved", {"id": str(saved.id)})

    return _stream(_follow(runs.start(chat.id, work)))


async def _follow(run: runs.Run) -> AsyncIterator[str]:
    async for event_type, data in run.follow():
        yield _sse(event_type, data)


@router.get("/{chat_id}/run")
async def follow_run(chat_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    """Re-attaches to the chat's running answer (after switching chats or reloading):
    replays its events from the start, then follows it. 204 when nothing is running."""
    chat = await _owned_chat(db, user, chat_id)
    run = runs.active(chat.id)
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return _stream(_follow(run))


@router.post("/{chat_id}/run/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(chat_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    """Stops the chat's running answer (the stop button)."""
    chat = await _owned_chat(db, user, chat_id)
    await runs.cancel(chat.id)


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

    await guard_budget(db, user)
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
        usage = llm.Usage()
        segments = []
        complete = False
        try:
            try:
                async for item in detail_stream(question or "", msg.content, sources, usage):
                    if isinstance(item, str):
                        yield _sse("delta", {"text": item})
                    else:
                        segments = [{"text": s.text, "keys": list(s.keys)} for s in item]
            except Exception as exc:
                logger.error("detail stream failed for message %s (%s)", message_pk, type(exc).__name__)
                yield _sse("error", {})
                return
            complete = True
        finally:
            try:
                async with get_sessionmaker()() as session:
                    if complete and (stored := await session.get(Message, message_pk)) is not None:
                        stored.meta = {**stored.meta, "detail": segments,
                                       "detail_cost_usd": round(usage.cost_usd, 4)}
                    await record_spend(session, user.id, "chat_detail", usage)
                    await session.commit()
            finally:
                llm.reset_runtime_config(token)
        yield _sse("detail", {"segments": segments})

    return _stream(events())
