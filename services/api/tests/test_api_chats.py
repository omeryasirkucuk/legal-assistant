import json
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from legal_api.chat.service import drop_unanswered
from legal_api.config import get_settings
from legal_api.db.app_models import Chat, Message
from legal_api.main import create_app

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))

get_settings().invite_code = "test-invite"
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


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_auth_and_chat_lifecycle():
    email = _email("test")
    async with await _client() as c:
        assert (await c.get("/chats")).status_code == 401
        r = await c.post("/auth/register", json={"email": email, "password": "secret-pass",
                                                  "name": "Test", "invite_code": "test-invite"})
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
        await owner.post("/auth/register", json={"email": email, "password": "secret-pass",
                                                  "name": "Owner", "invite_code": "test-invite"})
        chat = (await owner.post("/chats", json={"content": "x"})).json()
    async with await _client() as other:
        assert (await other.post("/auth/login", json={"email": email, "password": "wrong-pass"})
                ).status_code == 401
        await other.post("/auth/register", json={
            "email": _email("o"), "password": "secret-pass",
            "name": "Other", "invite_code": "test-invite"})
        assert (await other.get(f"/chats/{chat['id']}/messages")).status_code == 404


async def test_registration_requires_the_invite_code():
    async with await _client() as c:
        r = await c.post("/auth/register", json={
            "email": _email("x"), "password": "secret-pass",
            "name": "X", "invite_code": "wrong"})
        assert r.status_code == 403


async def test_an_unanswered_last_question_is_dropped():
    async with await _client() as c:
        await c.post("/auth/register", json={"email": _email("test"), "password": "secret-pass",
                                              "name": "T", "invite_code": "test-invite"})
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
