import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from legal_api.config import get_settings
from legal_api.locale import matter_terms
from legal_api.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "tr"
get_settings().invite_code = "test-invite"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    email = f"matter-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://test") as c:
        await c.post("/auth/register", json={"email": email, "password": "secret-pass",
                                              "name": "M", "invite_code": "test-invite"})
        yield c
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    await engine.dispose()


async def test_a_matter_gathers_its_chats_documents_and_deadlines(client):
    m = (await client.post("/matters", json={"client": "Client A", "subject": "Divorce"})).json()
    chat = (await client.post("/chats", json={"content": "Velayet", "matter_id": m["id"]})).json()
    assert chat["matter_id"] == m["id"]
    loose = (await client.post("/chats", json={"content": "Other"})).json()
    r = await client.put(f"/chats/{loose['id']}/matter", json={"matter_id": m["id"]})
    assert r.json()["matter_id"] == m["id"]
    doc = await client.post(f"/matters/{m['id']}/files",
                            files={"file": ("rapor.txt", b"Darp raporu.")})
    assert doc.status_code == 201
    soon = date.today() + timedelta(days=5)
    await client.post(f"/matters/{m['id']}/deadlines", json={"label": "Appeal", "due": str(soon)})
    late = date.today() + timedelta(days=40)
    await client.post(f"/matters/{m['id']}/deadlines", json={"label": "Hearing", "due": str(late)})

    detail = (await client.get(f"/matters/{m['id']}")).json()
    assert {c["id"] for c in detail["chats"]} == {chat["id"], loose["id"]}
    assert [d["name"] for d in detail["documents"]] == ["rapor.txt"]
    assert detail["next_deadline"]["label"] == "Appeal"
    listed = (await client.get("/matters")).json()
    assert listed[0]["next_deadline"]["due"] == str(soon)

    first = detail["deadlines"][0]["id"]
    await client.patch(f"/deadlines/{first}", json={"done": True})
    calendar = (await client.get("/deadlines")).json()
    assert [(c["label"], c["done"], c["client"]) for c in calendar] == [
        ("Appeal", True, "Client A"), ("Hearing", False, "Client A")]
    assert (await client.get(f"/matters/{m['id']}")).json()["next_deadline"]["label"] == "Hearing"

    # Deleting the file keeps its chats, outside any file.
    assert (await client.delete(f"/matters/{m['id']}")).status_code == 204
    chats = (await client.get("/chats")).json()
    assert all(c["matter_id"] is None for c in chats) and len(chats) == 2
    assert (await client.get("/deadlines")).json() == []


async def test_matters_are_private(client):
    m = (await client.post("/matters", json={"client": "X"})).json()
    assert (await client.get(f"/matters/{uuid.uuid4()}")).status_code == 404
    assert (await client.patch(f"/matters/{m['id']}", json={"notes": "n"})).json()["notes"] == "n"


def test_the_matter_is_described_to_the_model():
    from legal_api.db.matter_models import Matter
    from legal_api.matters.service import context
    m = Matter(client="Client A", subject="Divorce", opponent="", court="Family Court 2",
               case_no="", notes="Two children.")
    text_ = context(m, []).text
    assert "Client A" in text_ and "Family Court 2" in text_ and "Two children." in text_
    assert matter_terms()["fields"]["opponent"] not in text_


async def test_the_calendar_knows_holidays_and_the_recess(client):
    y = (await client.get("/holidays/2026")).json()
    assert y["covered"] and y["recess_start"] == "2026-07-20" and y["recess_end"] == "2026-08-31"
    names = {h["day"]: (h["name"], h["half"]) for h in y["holidays"]}
    assert names["2026-10-29"][0].startswith("Cumhuriyet") and names["2026-10-28"][1]
    assert not (await client.get("/holidays/2031")).json()["covered"]


async def test_the_form_asks_the_server(client):
    r = (await client.post("/deadlines/calculate", json={
        "received": "2026-11-02", "service": "electronic", "amount": 2, "unit": "week",
        "branch": "civil"})).json()
    assert r["served"] == "2026-11-07" and r["due"] == "2026-11-23"
    assert [s["code"] for s in r["steps"]] == ["period", "weekend"]


async def test_a_deadline_keeps_its_branch(client):
    m = (await client.post("/matters", json={"client": "Branch test"})).json()
    d = (await client.post(f"/matters/{m['id']}/deadlines", json={
        "label": "Objection", "due": "2026-12-01", "branch": "enforcement"})).json()
    assert d["branch"] == "enforcement"
    plain = (await client.post(f"/matters/{m['id']}/deadlines", json={
        "label": "Hearing", "due": "2026-12-02"})).json()
    assert plain["branch"] is None


async def test_search_finds_files_and_what_is_in_their_documents(client):
    f = json.loads((FIXTURES / "matter_search.json").read_text(encoding="utf-8"))
    m = (await client.post("/matters", json={"client": f["client"], "subject": f["subject"],
                                              "notes": f["notes"]})).json()
    await client.post(f"/matters/{m['id']}/files", files={"file": (
        f["file_name"], f["file_text"].encode(), "text/plain")})
    by_note = (await client.get("/matters/search", params={"q": f["query_note"]})).json()
    assert [x["client"] for x in by_note["matters"]] == [f["client"]]
    by_text = (await client.get("/matters/search", params={"q": f["query_text"]})).json()
    assert by_text["documents"][0]["name"] == f["file_name"]
    assert f["mark"] in by_text["documents"][0]["snippet"]
    none = (await client.get("/matters/search", params={"q": f["query_none"]})).json()
    assert none == {"matters": [], "documents": []}


async def test_calendar_events_keep_case_links_and_reminder_state(client):
    from datetime import UTC, datetime

    matter = (await client.post("/matters", json={"client": "Duruşma dosyası"})).json()
    future = (datetime.now(UTC).date() + timedelta(days=20)).isoformat()
    hearing = {"kind": "hearing", "label": " Ön inceleme ", "due": future,
               "matter_id": matter["id"], "start_time": "14:15", "end_time": "15:00",
               "location": "Salon 3", "reminder_minutes": 30}
    r = await client.post("/calendar/events", json=hearing)
    assert r.status_code == 201, r.text
    event = r.json()
    assert event["label"] == "Ön inceleme"
    assert event["remind_at"] == f"{future}T10:45:00Z"
    assert (await client.get(f"/matters/{matter['id']}")).json()["events"] == [event]
    ics = await client.get(f"/calendar/events/{event['id']}/ics")
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    day_stamp = future.replace("-", "")
    assert f"DTSTART:{day_stamp}T111500Z\r\n" in ics.text
    assert f"DTEND:{day_stamp}T120000Z\r\n" in ics.text
    assert f"TRIGGER;VALUE=DATE-TIME:{day_stamp}T104500Z\r\n" in ics.text
    assert (await client.get("/calendar/reminders")).json() == []
    prefix = "/calendar/events"
    event_url = f"{prefix}/{event['id']}"
    invalid = await client.put(event_url, json={**hearing, "end_time": "13:00"})
    assert invalid.status_code == 422
    assert (await client.post(prefix, json={**hearing, "label": "  "})).status_code == 422
    assert (await client.post(prefix, json={**hearing, "start_time": "14:15+03:00"})).status_code == 422

    day = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    fields = {"kind": "reminder", "label": "Avukatı ara", "due": day, "reminder_minutes": 0}
    personal = (await client.post(prefix, json=fields)).json()
    assert personal["remind_at"] == f"{day}T06:00:00Z"
    assert personal["matter_id"] is None
    personal_url = f"{prefix}/{personal['id']}"
    assert [row["id"] for row in (await client.get("/calendar/reminders")).json()] == [personal["id"]]

    done = (await client.patch(personal_url, json={"done": True})).json()
    assert done["done"] and (await client.get("/calendar/reminders")).json() == []
    await client.patch(personal_url, json={"done": False})
    dismissed = (await client.patch(personal_url, json={"dismiss_reminder_at": personal["remind_at"]})).json()
    assert dismissed["reminder_dismissed"] and (await client.get("/calendar/reminders")).json() == []
    renamed = (await client.put(personal_url, json={**fields, "label": "Deniz’i ara"})).json()
    assert renamed["reminder_dismissed"]
    rescheduled = (await client.put(personal_url, json={**fields, "start_time": "10:00"})).json()
    assert not rescheduled["reminder_dismissed"]
    stale = await client.patch(personal_url, json={"dismiss_reminder_at": personal["remind_at"]})
    assert not stale.json()["reminder_dismissed"]
    assert (await client.get("/calendar/reminders")).json()[0]["remind_at"] == f"{day}T07:00:00Z"

    assert (await client.delete(personal_url)).status_code == 204
    assert (await client.delete(f"/matters/{matter['id']}")).status_code == 204
    items = (await client.get(prefix)).json()
    assert len(items) == 1 and items[0]["id"] == event["id"] and items[0]["matter_id"] is None


async def test_calendar_events_and_links_are_private(client):
    matter = (await client.post("/matters", json={"client": "Private"})).json()
    body = {"kind": "reminder", "label": "Private reminder", "due": "2026-11-23"}
    event = (await client.post("/calendar/events", json=body)).json()
    email = f"calendar-{uuid.uuid4().hex[:8]}@example.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as other:
            r = await other.post("/auth/register", json={"email": email, "password": "secret-pass",
                                                         "name": "Other", "invite_code": "test-invite"})
            assert r.status_code == 201
            assert (await other.get("/calendar/events")).json() == []
            assert (await other.get("/calendar/reminders")).json() == []
            assert (await other.post("/calendar/events", json={**body, "matter_id": matter["id"]})).status_code == 404
            url = f"/calendar/events/{event['id']}"
            assert (await other.get(f"{url}/ics")).status_code == 404
            assert (await other.put(url, json=body)).status_code == 404
            assert (await other.patch(url, json={"done": True})).status_code == 404
            assert (await other.delete(url)).status_code == 404
    finally:
        engine = create_async_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
        await engine.dispose()
