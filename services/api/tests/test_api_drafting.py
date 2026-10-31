import asyncio
import json
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from legal_api.api import drafting as drafting_api
from legal_api.config import get_settings
from legal_api.drafting import store as drafting_store
from legal_api.drafting.sample_profile import SampleProfile
from legal_api.main import create_app

TR = json.loads((Path(__file__).parent / "fixtures" / "tr" / "test_strings.json").read_text(encoding="utf-8"))

get_settings().invite_code = "test-invite"
FORMAL = (Path(__file__).parent / "fixtures" / "tr" / "petition_formal.txt").read_text(
    encoding="utf-8")


# The model's reading of a sample (drafting/sample_profile.py), stood in for by the file name
# so tests make no model call.
READINGS = {"karar.txt": SampleProfile(is_petition=False),
            "emir.txt": SampleProfile(is_petition=False),
            "is.txt": SampleProfile(True, "dava", "labour", "iscilik", TR["api_drafting_1"])}


async def _read(title, text, usage):
    return READINGS.get(title, SampleProfile(True, "dava", "tenancy", "tahliye", "tahliye"))


@pytest.fixture(autouse=True)
def no_model_reading(monkeypatch):
    monkeypatch.setattr(drafting_api, "analyze", _read)
    monkeypatch.setattr(drafting_store, "analyze", _read)


@pytest.fixture
async def client():
    email = f"draft-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://test") as c:
        await c.post("/auth/register", json={"email": email, "password": "secret-pass",
                                              "name": "D", "invite_code": "test-invite"})
        yield c
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    await engine.dispose()


async def test_a_sample_shapes_the_profile(client):
    before = (await client.get("/drafting/profile")).json()
    assert before["samples"] == 0 and before["types"]["dava"]["learnt_from"] == 0
    r = await client.post("/drafting/samples", data={"petition_type": "dava"},
                          files={"file": ("kira.txt", FORMAL.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    after = (await client.get("/drafting/profile")).json()
    assert after["types"]["dava"]["learnt_from"] == 1
    assert after["types"]["dava"]["register"] == "formal"
    rules = await client.put("/drafting/profile/rules", json={"rules": [TR["api_drafting_2"], " "]})
    assert rules.json() == {"rules": [TR["api_drafting_3"]]}
    sid = r.json()["id"]
    assert (await client.delete(f"/drafting/samples/{sid}")).status_code == 204


async def test_short_or_unknown_files_are_refused(client):
    r = await client.post("/drafting/samples/text", json={"title": "x", "text": TR["api_drafting_4"]})
    assert r.status_code == 422
    r = await client.post("/drafting/samples", files={"file": ("a.exe", b"x")})
    assert r.status_code == 415


async def test_a_uyap_file_can_be_a_sample(client):
    from legal_api.drafting.export import render
    r = await client.post("/drafting/samples", data={"petition_type": "dava"},
                          files={"file": ("dilekce.udf", render(FORMAL, "udf"))})
    assert r.status_code == 201, r.text
    # A damaged UYAP file is refused, not a server error.
    r = await client.post("/drafting/samples", files={"file": ("bozuk.udf", b"not a zip")})
    assert r.status_code == 422


async def test_samples_are_sorted_out_one_by_one(client):
    from legal_api.drafting.export import render
    docs = Path(__file__).parent / "fixtures" / "tr" / "documents"
    labour = (docs / "labour_petition.txt").read_bytes()
    r = await client.post("/drafting/samples", files={"file": ("is.txt", labour)})
    assert r.status_code == 201, r.text
    sample = r.json()
    assert sample["petition_type"] == "dava" and sample["area"] == "labour"
    assert sample["matter"] == TR["api_drafting_5"]
    assert sample["format"] == "text"
    # The same petition again, and a court decision, are not added.
    again = await client.post("/drafting/samples", files={"file": ("kopya.txt", labour)})
    assert again.status_code == 409 and again.json()["detail"] == "duplicate"
    decision = (docs / "family_decision.txt").read_text(encoding="utf-8") * 2
    r = await client.post("/drafting/samples", files={"file": ("karar.txt", decision.encode())})
    assert r.status_code == 422 and r.json()["detail"] == "not_petition"
    order = (docs / "enforcement_order.txt").read_text(encoding="utf-8") * 2
    r = await client.post("/drafting/samples", files={"file": ("emir.txt", order.encode())})
    assert r.status_code == 422 and r.json()["detail"] == "not_petition"
    formal = await client.post("/drafting/samples", files={"file": ("kira.udf", render(FORMAL, "udf"))})
    assert formal.json()["petition_type"] == "dava" and formal.json()["format"] == "udf"
    # The lawyer corrects the type worked out.
    r = await client.put(f"/drafting/samples/{sample['id']}", json={"petition_type": "cevap"})
    assert r.json()["petition_type"] == "cevap"


async def test_an_edited_copy_is_asked_about_and_can_replace_the_old_one(client):
    first = (await client.post("/drafting/samples", files={"file": ("a.txt", FORMAL.encode())})).json()
    edited = FORMAL.replace(TR["api_drafting_6"],
                            TR["api_drafting_7"])
    r = await client.post("/drafting/samples", files={"file": ("a2.txt", edited.encode())})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "similar"
    assert r.json()["detail"]["id"] == first["id"]
    r = await client.post("/drafting/samples", data={"replace": first["id"]},
                          files={"file": ("a2.txt", edited.encode())})
    assert r.status_code == 201
    titles = [s["title"] for s in (await client.get("/drafting/samples")).json()]
    assert titles == ["a2.txt"]
    other = edited.replace("kira", TR["api_drafting_8"]).replace("Kira", TR["api_drafting_9"])
    r = await client.post("/drafting/samples", data={"keep": "true"},
                          files={"file": ("b.txt", other.encode())})
    assert r.status_code == 201


async def test_autosaves_keep_the_text_and_the_style_is_learnt_once(client, monkeypatch):
    from legal_api.db.session import get_sessionmaker
    learnt = []

    async def remember(user_id, before, after, petition_type):
        learnt.append((before, after))

    monkeypatch.setattr(drafting_api.memory, "learn_from_edit", remember)
    me = (await client.get("/auth/me")).json()
    async with get_sessionmaker()() as db:
        draft = await drafting_store.save_draft(db, uuid.UUID(me["id"]), None, uuid.uuid4(),
                                                "other", "Test", "First text.", "docx")
    for edited in ("First text, edited.", "First text, edited twice."):
        r = await client.put(f"/drafts/{draft.id}", json={"text": edited, "learn": False})
        assert r.status_code == 200 and r.json()["text"] == edited
    assert learnt == []
    assert (await client.post(f"/drafts/{draft.id}/learn")).status_code == 204
    await asyncio.sleep(0)
    assert learnt == [("First text.", "First text, edited twice.")]
    await client.post(f"/drafts/{draft.id}/learn")
    await asyncio.sleep(0)
    assert len(learnt) == 1
