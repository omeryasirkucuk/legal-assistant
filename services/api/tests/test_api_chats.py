import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from legal_api.agent import pipeline
from legal_api.agent.answer import Event
from legal_api.api import chats
from legal_api.chat.service import drop_unanswered
from legal_api.config import get_settings
from legal_api.db.app_models import Chat, Message
from legal_api.main import create_app
from legal_api.retrieval.statutes import StatuteHit
from tests.accounts import register_invited

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))

_created: list[str] = []


def _email(prefix: str) -> str:
    """A fresh address; its user (and, by cascade, its chats) is deleted after the test."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    _created.append(email)
    return email


@pytest.fixture(autouse=True)
async def _delete_test_users():
    yield
    if not _created:
        return
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = ANY(:emails)"),
                           {"emails": list(_created)})
    await engine.dispose()
    _created.clear()


async def test_answer_spend_survives_chat_deletion(monkeypatch):
    title_started = asyncio.Event()
    title_cancelled = asyncio.Event()

    async def title(_question, _usage):
        title_started.set()
        try:
            await asyncio.Future()
        finally:
            title_cancelled.set()

    async def answer(_message, _history, _previous, result, *_args, usage, workspace, **_kwargs):
        await title_started.wait()
        usage.record("test", SimpleNamespace(cost=0.012), "write")
        result["result"] = SimpleNamespace(
            text="Answer", structure=dict, usage=usage, timings={}, trace={}, ledger=[],
        )
        yield Event("final", {"text": "Answer"})

    monkeypatch.setattr(chats, "generate_title", title)
    monkeypatch.setattr(chats, "turn_events", answer)
    async with await _client() as c:
        await register_invited(c, _email("test"), "Test")
        chat_id = (await c.post("/chats", json={"content": "Question"})).json()["id"]
        response = await c.post(f"/chats/{chat_id}/messages", json={"content": "Question"})
        assert "event: saved" in response.text
        assert title_cancelled.is_set()
        assert (await c.get(f"/chats/{chat_id}/messages")).json()[-1]["content"] == "Answer"
        assert (await c.get("/chats/stats/today")).json()["cost_usd"] == 0.012
        assert (await c.delete(f"/chats/{chat_id}")).status_code == 204
        assert (await c.get("/chats/stats/today")).json()["cost_usd"] == 0.012


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_auth_and_chat_lifecycle():
    email = _email("test")
    async with await _client() as c:
        assert (await c.get("/chats")).status_code == 401
        r = await register_invited(c, email, "Test")
        assert r.status_code == 201
        assert (await c.get("/auth/me")).json()["email"] == email

        chat = (await c.post("/chats", json={"content": "Kira tahliye sorusu " * 10})).json()
        assert len(chat["title"]) <= 60
        assert next(x["id"] for x in (await c.get("/chats")).json()) == chat["id"]

        renamed = await c.patch(f"/chats/{chat['id']}", json={"title": "Kira"})
        assert renamed.json()["title"] == "Kira"
        assert (await c.get(f"/chats/{chat['id']}/messages")).json() == []
        assert (await c.delete(f"/chats/{chat['id']}")).status_code == 204
        assert (await c.get(f"/chats/{chat['id']}/messages")).status_code == 404


async def test_wrong_password_and_foreign_chat_are_rejected():
    email = _email("test")
    async with await _client() as owner:
        await register_invited(owner, email, "Owner")
        chat = (await owner.post("/chats", json={"content": "x"})).json()
    async with await _client() as other:
        assert (await other.post("/auth/login", json={"email": email, "password": "wrong-pass"})
                ).status_code == 401
        await register_invited(other, _email("o"), "Other")
        assert (await other.get(f"/chats/{chat['id']}/messages")).status_code == 404


async def test_registration_requires_the_invite_code():
    async with await _client() as c:
        r = await c.post("/auth/register", json={
            "email": _email("x"), "password": "secret-pass",
            "name": "X", "invite_code": "wrong"})
        assert r.status_code == 403


async def test_an_unanswered_last_question_is_dropped():
    async with await _client() as c:
        await register_invited(c, _email("test"), "T")
        chat_id = (await c.post("/chats", json={"content": "x"})).json()["id"]
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        chat = await db.get(Chat, uuid.UUID(chat_id))
        db.add(Message(chat_id=chat.id, role="user", content=TR["api_chats_1"], meta={}))
        await db.commit()
        await drop_unanswered(db, chat)
        left = (await db.scalars(text("SELECT role FROM messages WHERE chat_id = :c")
                                 .bindparams(c=chat.id))).all()
        assert left == []
    await engine.dispose()


async def test_change_password_keeps_current_session_and_invalidates_other_sessions():
    email = _email("password-test")
    old, new = "original-test-secret", "new-test-secret"
    change = {"current_password": old, "new_password": new}
    async with await _client() as owner, await _client() as other, await _client() as guest:
        registered = await register_invited(owner, email, "User", old)
        assert registered.status_code == 201 and not registered.json()["is_admin"]
        assert (await other.post("/auth/login", json={"email": email, "password": old})).status_code == 200
        assert (await guest.put("/auth/password", json=change)).status_code == 401
        assert (await owner.put("/auth/password", json={**change, "current_password": "wrong"})).status_code == 403
        assert (await owner.put("/auth/password", json={**change, "new_password": "short"})).status_code == 422
        assert (await owner.put("/auth/password", json={**change, "new_password": old})).status_code == 409

        response = await owner.put("/auth/password", json=change)
        assert response.status_code == 204
        assert response.content == b""
        assert (await owner.get("/auth/me")).status_code == 200
        assert (await other.get("/auth/me")).status_code == 401
        assert (await other.post("/auth/login", json={"email": email, "password": old})).status_code == 401
        assert (await other.post("/auth/login", json={"email": email, "password": new})).status_code == 200


async def test_stalled_answer_closes_the_stream_and_can_be_retried(monkeypatch):
    cleaned = asyncio.Event()

    async def stalled(*_args, **_kwargs):
        try:
            yield Event("step", {"name": "analyse", "state": "active"})
            await asyncio.Future()
        finally:
            cleaned.set()

    async with await _client() as c:
        await register_invited(c, _email("timeout"), "Test")
        chat_id = (await c.post("/chats", json={"content": "Merhaba"})).json()["id"]
        with monkeypatch.context() as patch:
            patch.setattr(chats, "ANSWER_TIMEOUT_S", 0.05)
            patch.setattr(chats, "turn_events", stalled)
            response = await c.post(f"/chats/{chat_id}/messages", json={"content": "Merhaba"})
        assert 'event: error\ndata: {"timed_out": true}' in response.text
        assert cleaned.is_set()
        assert (await c.get(f"/chats/{chat_id}/run")).status_code == 204
        retried = await c.post(f"/chats/{chat_id}/messages", json={"content": "Merhaba"})
        assert "event: saved" in retried.text


async def test_explicit_article_text_is_served_with_its_source(monkeypatch):
    async def article(_connection, law, label):
        assert (law, label) == ("6098", "344")
        return StatuteHit(1, law, "Türk Borçlar Kanunu", "s", label, "",
                          "Yerel dizinden alınan örnek madde metni.", "https://example.com/article",
                          datetime.now(UTC))

    async def no_model(*_args, **_kwargs):
        pytest.fail("An explicit article text request should not invoke a model")

    monkeypatch.setattr(pipeline, "get_article", article)
    monkeypatch.setattr(pipeline, "understand", no_model)
    monkeypatch.setattr(chats, "generate_title", no_model)
    monkeypatch.setattr(chats, "style_book", no_model)
    question = "6098 sayılı Kanun’un 344. maddesinin metnini göster"
    async with await _client() as c:
        await register_invited(c, _email("article"), "Test")
        chat_id = (await c.post("/chats", json={"content": question})).json()["id"]
        response = await c.post(f"/chats/{chat_id}/messages", json={"content": question})
        assert "event: evidence" in response.text and "event: saved" in response.text
        assert '"first_delta_s":' in response.text
        messages = (await c.get(f"/chats/{chat_id}/messages")).json()
        assert "Yerel dizinden alınan örnek madde metni." in messages[-1]["content"]
        assert messages[-1]["evidence"][0]["url"] == "https://example.com/article"
