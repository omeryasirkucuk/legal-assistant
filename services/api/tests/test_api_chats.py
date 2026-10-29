import uuid

from httpx import ASGITransport, AsyncClient

from legal_api.config import get_settings
from legal_api.main import create_app

get_settings().invite_code = "test-invite"


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_auth_and_chat_lifecycle():
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
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
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    async with await _client() as owner:
        await owner.post("/auth/register", json={"email": email, "password": "secret-pass",
                                                  "name": "Owner", "invite_code": "test-invite"})
        chat = (await owner.post("/chats", json={"content": "x"})).json()
    async with await _client() as other:
        assert (await other.post("/auth/login", json={"email": email, "password": "wrong-pass"})
                ).status_code == 401
        await other.post("/auth/register", json={
            "email": f"o-{uuid.uuid4().hex[:8]}@example.com", "password": "secret-pass",
            "name": "Other", "invite_code": "test-invite"})
        assert (await other.get(f"/chats/{chat['id']}/messages")).status_code == 404


async def test_registration_requires_the_invite_code():
    async with await _client() as c:
        r = await c.post("/auth/register", json={
            "email": f"x-{uuid.uuid4().hex[:8]}@example.com", "password": "secret-pass",
            "name": "X", "invite_code": "wrong"})
        assert r.status_code == 403
