import json
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from legal_api.config import get_settings
from legal_api.drafting import memory, store
from legal_api.main import create_app

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))

get_settings().invite_code = "test-invite"


@pytest.fixture
async def session_and_user():
    email = f"mem-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://test") as c:
        await c.post("/auth/register", json={"email": email, "password": "secret-pass",
                                              "name": "M", "invite_code": "test-invite"})
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        user = (await db.execute(text("SELECT id FROM users WHERE email = :e"),
                                 {"e": email})).scalar_one()
        yield db, user
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    await engine.dispose()


def test_case_material_is_not_a_preference():
    assert memory.acceptable(TR["style_memory_1"])
    assert not memory.acceptable(TR["style_memory_2"])
    assert not memory.acceptable(TR["style_memory_3"])


async def test_a_preference_is_used_only_once_confirmed(session_and_user):
    db, user = session_and_user
    pref = TR["style_memory_4"]
    await memory.remember(db, user, [pref], "dava")
    assert await memory.relevant(db, user, TR["style_memory_5"], None) == []
    # The same preference in other words, from another edit, counts as seen again.
    await memory.remember(db, user, [TR["style_memory_6"]],
                          "dava")
    assert await memory.relevant(db, user, TR["style_memory_7"], None) == [pref]


async def test_reset_forgets_what_was_learnt(session_and_user):
    db, user = session_and_user
    await memory.remember(db, user, [TR["style_memory_8"]] * 2, None)
    await store.choose_style(db, user, "short", "plain")
    await store.reset_learning(db, user)
    book = await store.style_book(db, user, TR["style_memory_9"])
    assert book.learnt == [] and book.preferences.length is None
