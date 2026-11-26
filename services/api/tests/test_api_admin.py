import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from legal_api.auth import session_token
from legal_api.config import get_settings
from legal_api.db.app_models import LlmSpend, RegistrationInvite, User
from legal_api.db.session import get_sessionmaker
from legal_api.main import create_app
from legal_api.spend import start_of_utc_day


@pytest.fixture
async def accounts():
    sessionmaker = get_sessionmaker()
    users = [
        User(id=uuid4(), name=name, email=f"{uuid4()}@example.com", is_admin=admin,
             password_hash="")
        for name, admin in [("Admin", True), ("Account with spend", False), ("New account", False)]
    ]
    async with sessionmaker() as db:
        db.add_all(users)
        await db.flush()
        start = start_of_utc_day()
        db.add_all([
            LlmSpend(user_id=users[1].id, purpose="chat_answer", cost_usd=0.10, created_at=start),
            LlmSpend(user_id=users[1].id, purpose="sample_read", cost_usd=0.02, created_at=start),
            LlmSpend(user_id=users[1].id, purpose="detail", cost_usd=0.30,
                     created_at=start - timedelta(seconds=1)),
        ])
        await db.commit()
    yield users
    async with sessionmaker() as db:
        await db.execute(delete(User).where(User.id.in_([user.id for user in users])))
        await db.commit()


def _client(user: User | None = None):
    cookies = {"session": session_token(user.id)} if user is not None else None
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test",
                       cookies=cookies)


async def test_admin_lists_accounts_and_all_recorded_spend(accounts):
    admin, spender, new = accounts
    async with _client() as guest, _client(spender) as member, _client(admin) as operator:
        assert (await guest.get("/admin/users")).status_code == 401
        assert (await member.get("/admin/users")).status_code == 403
        assert (await member.patch(f"/admin/users/{spender.id}/role",
                                   json={"is_admin": True})).status_code == 403
        response = await operator.get("/admin/users")
        assert response.status_code == 200
        summary = {row["id"]: row for row in response.json()}
        assert summary[str(spender.id)] == {
            "id": str(spender.id), "name": spender.name, "email": spender.email, "is_admin": False,
            "today_cost_usd": pytest.approx(0.12), "total_cost_usd": pytest.approx(0.42),
        }
        assert summary[str(new.id)]["today_cost_usd"] == summary[str(new.id)]["total_cost_usd"] == 0


async def test_role_changes_apply_to_existing_sessions(accounts):
    admin, member, _ = accounts
    async with _client(admin) as operator, _client(member) as participant:
        admin_role = f"/admin/users/{admin.id}/role"
        member_role = f"/admin/users/{member.id}/role"
        assert (await operator.patch(member_role, json={"is_admin": "true"})).status_code == 422
        assert (await operator.patch(member_role, json={"is_admin": True})).json() == {"is_admin": True}
        assert (await participant.get("/admin/users")).status_code == 200
        assert (await participant.patch(admin_role, json={"is_admin": False})).json() == {"is_admin": False}
        assert (await operator.get("/admin/users")).status_code == 403
        assert (await participant.get("/auth/me")).json()["is_admin"] is True


async def test_the_only_admin_cannot_be_demoted(accounts):
    admin, _, _ = accounts
    async with get_sessionmaker()() as db:
        other = await db.scalar(select(User.id).where(
            User.id != admin.id, User.is_admin.is_(True)
        ).limit(1))
    if other is not None:
        pytest.skip("Requires a database without preexisting administrator accounts")

    async with _client(admin) as operator:
        response = await operator.patch(f"/admin/users/{admin.id}/role", json={"is_admin": False})
        assert response.status_code == 409
        assert (await operator.get("/auth/me")).json()["is_admin"] is True


async def test_admin_invites_are_unique_bound_to_email_and_single_use(accounts, monkeypatch):
    admin, member, _ = accounts
    email, other_email = (f"{uuid4()}@example.com" for _ in range(2))
    monkeypatch.setattr(get_settings(), "invite_code", "test-bootstrap")
    registration = {"email": email, "name": "Invitee", "password": "test-pass-123"}

    try:
        async with _client(admin) as operator, _client(member) as participant, _client() as guest:
            path = "/admin/invites"
            recipient = {"email": email.upper()}
            assert (await guest.post(path, json=recipient)).status_code == 401
            assert (await participant.post(path, json=recipient)).status_code == 403
            assert (await operator.post(path, json={"email": "invalid"})).status_code == 422
            assert (await operator.post(path, json={"email": member.email})).status_code == 409

            first = await operator.post(path, json=recipient)
            second = await operator.post(path, json={"email": other_email})
            assert first.status_code == second.status_code == 201
            assert first.headers["Cache-Control"] == "no-store"
            assert first.json()["email"] == email
            code = first.json()["code"]
            assert code != second.json()["code"]

            register = "/auth/register"
            assert (await guest.post(register, json={
                **registration, "invite_code": "test-bootstrap",
            })).status_code == 403
            assert (await guest.post(register, json={
                **registration, "email": other_email, "invite_code": code,
            })).status_code == 403

            payload = {**registration, "email": email.upper(), "invite_code": code}
            async with _client() as concurrent:
                results = await asyncio.gather(
                    guest.post(register, json=payload),
                    concurrent.post(register, json=payload),
                )
            assert sorted(r.status_code for r in results) == [201, 403]
            created = next(r.json() for r in results if r.status_code == 201)
            assert created["email"] == email and created["is_admin"] is False
            assert (await guest.post(register, json=payload)).status_code == 403

            other = await guest.post(register, json={
                **registration, "email": other_email, "invite_code": second.json()["code"],
            })
            assert other.status_code == 201
    finally:
        async with get_sessionmaker()() as db:
            await db.execute(delete(RegistrationInvite).where(RegistrationInvite.email.in_([email, other_email])))
            await db.execute(delete(User).where(User.email.in_([email, other_email])))
            await db.commit()


async def test_bootstrap_creates_only_the_first_admin(monkeypatch):
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        if await db.scalar(select(User.id).limit(1)) is not None:
            pytest.skip("Requires a database without preexisting accounts")

    monkeypatch.setattr(get_settings(), "invite_code", "test-bootstrap")
    email, other_email = (f"{uuid4()}@example.com" for _ in range(2))
    payload = {"email": email, "name": "First", "password": "test-pass-123",
               "invite_code": "test-bootstrap"}
    try:
        async with _client() as guest:
            result = await guest.post("/auth/register", json=payload)
            assert result.status_code == 201 and result.json()["is_admin"] is True
            blocked = await guest.post("/auth/register", json={**payload, "email": other_email})
            assert blocked.status_code == 403
    finally:
        async with sessionmaker() as db:
            await db.execute(delete(User).where(User.email.in_([email, other_email])))
            await db.commit()
