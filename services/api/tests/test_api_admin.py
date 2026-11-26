from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from legal_api.auth import session_token
from legal_api.db.app_models import LlmSpend, User
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
