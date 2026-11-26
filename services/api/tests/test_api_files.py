import base64
import io
import json
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from legal_api.config import get_settings
from legal_api.db.file_models import StoredFile
from legal_api.db.session import get_sessionmaker
from legal_api.files import store
from legal_api.files.store import encrypt_existing
from legal_api.main import create_app
from tests.accounts import register_invited

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "tr" / "file_upload.json")
                    .read_text(encoding="utf-8"))


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    email = f"files-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://test") as c:
        await register_invited(c, email, "F")
        yield c
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    await engine.dispose()


async def test_upload_list_download_delete(client):
    r = await client.post("/files", files={"file": (SAMPLE["name"], SAMPLE["text"].encode())})
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["format"] == "text" and {f["kind"], f["area"]} <= {"other", "notice", "tenancy"}
    assert f["readable"] and f["origin"] == "upload" and f["size"] == len(SAMPLE["text"].encode())
    assert [x["id"] for x in (await client.get("/files")).json()] == [f["id"]]
    assert (await client.get("/files/usage")).json()["used_bytes"] == f["size"]
    body = await client.get(f"/files/{f['id']}")
    assert body.content.decode() == SAMPLE["text"] and SAMPLE["name"] in body.headers["content-disposition"]
    assert (await client.delete(f"/files/{f['id']}")).status_code == 204
    assert (await client.get("/files/usage")).json()["used_bytes"] == 0


async def test_the_quota_is_enforced(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "user_storage_bytes", 10)
    r = await client.post("/files", files={"file": ("a.txt", b"x" * 11)})
    assert r.status_code == 507


async def test_existing_and_new_files_are_sealed_without_changing_downloads(client, monkeypatch):
    settings = get_settings()
    data = b"Synthetic client document"
    legacy = (await client.post("/files", files={"file": ("original.txt", data)})).json()
    monkeypatch.setattr(settings, "document_encryption_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    async with get_sessionmaker()() as db:
        assert await encrypt_existing(db, file_ids=[uuid.UUID(legacy["id"])]) == 1
        assert await encrypt_existing(db, file_ids=[uuid.UUID(legacy["id"])]) == 0
    monkeypatch.setattr(settings, "data_mode", "protected")
    new = (await client.post("/files", files={"file": ("new.txt", data)})).json()

    for item in [legacy, new]:
        async with get_sessionmaker()() as db:
            row = await db.get(StoredFile, uuid.UUID(item["id"]))
            assert row.encrypted and item["name"] not in row.path
            path = settings.storage_dir / row.path
            assert data not in path.read_bytes()
            assert not (settings.storage_dir / "users" / str(row.user_id) / str(row.id)).exists()
        response = await client.get(f"/files/{item['id']}")
        assert response.content == data and response.headers["cache-control"] == "no-store"
        assert (await client.delete(f"/files/{item['id']}")).status_code == 204
        assert not path.exists()


async def test_non_previewable_upload_is_download_only(client):
    data = b"<p>Synthetic document fixture</p>"
    file_id = (await client.post("/files", files={"file": ("sample.html", data, "text/html")})).json()["id"]
    response = await client.get(f"/files/{file_id}?inline=true")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_file_is_renamed_keeping_its_extension(client):
    f = (await client.post("/files", files={"file": ("notice.txt", b"The rent was overdue.")})).json()
    renamed = (await client.patch(f"/files/{f['id']}", json={"name": "Final notice"})).json()
    assert renamed["name"] == "Final notice.txt"


async def test_editing_an_added_document_opens_one_editable_copy(client):
    f = (await client.post("/files", files={"file": ("contract.txt",
         b"CENTRAL CIVIL COURT\n\nThe tenant did not pay the rent.")})).json()
    first = (await client.post(f"/drafts/from-file/{f['id']}")).json()
    again = (await client.post(f"/drafts/from-file/{f['id']}")).json()
    assert first["id"] == again["id"] and first["title"] == "contract"
    assert first["doc"]["content"][0]["attrs"]["textAlign"] == "center"
    original = await client.get(f"/files/{f['id']}")
    assert original.content == b"CENTRAL CIVIL COURT\n\nThe tenant did not pay the rent."


async def test_folders_hold_files_and_give_them_back_when_deleted(client):
    top = (await client.post("/folders", json={"name": "Clients"})).json()
    inner = (await client.post("/folders", json={"name": "2026", "parent_id": top["id"]})).json()
    f = (await client.post("/files", data={"folder_id": inner["id"]},
                           files={"file": ("a.txt", b"Some text.")})).json()
    assert f["folder_id"] == inner["id"]
    cycle = await client.patch(f"/folders/{top['id']}", json={"parent_id": inner["id"]})
    assert cycle.status_code == 422
    assert (await client.delete(f"/folders/{inner['id']}")).status_code == 204
    moved = next(x for x in (await client.get("/files")).json() if x["id"] == f["id"])
    assert moved["folder_id"] == top["id"]
    out = (await client.patch(f"/files/{f['id']}", json={"to_top": True})).json()
    assert out["folder_id"] is None


async def test_a_file_can_be_given_to_a_case_and_previewed(client):
    m = (await client.post("/matters", json={"client": "Client B"})).json()
    f = (await client.post("/files", files={"file": ("report.txt", b"CENTRAL COURT\n\nThe report.")})).json()
    given = (await client.patch(f"/files/{f['id']}", json={"matter_id": m["id"]})).json()
    assert given["matter_id"] == m["id"]
    names = [d["name"] for d in (await client.get(f"/matters/{m['id']}")).json()["documents"]]
    assert "report.txt" in names
    shown = (await client.get(f"/files/{f['id']}/preview")).json()
    assert shown["kind"] == "document" and shown["doc"]["content"][0]["attrs"]["textAlign"] == "center"
    png = (await client.post("/files", files={"file": ("x.png", b"\x89PNG\r\n\x1a\n")})).json()
    assert (await client.get(f"/files/{png['id']}/preview")).json()["kind"] == "image"


async def test_a_copy_gets_a_free_name_in_its_folder(client):
    f = (await client.post("/files", files={"file": ("memo.txt", b"Some text.")})).json()
    first = (await client.post(f"/files/{f['id']}/copy", json={})).json()
    second = (await client.post(f"/files/{f['id']}/copy", json={})).json()
    assert (first["name"], second["name"]) == ("memo (2).txt", "memo (3).txt")
    folder = (await client.post("/folders", json={"name": "Elsewhere"})).json()
    there = (await client.post(f"/files/{f['id']}/copy", json={"folder_id": folder["id"]})).json()
    assert there["name"] == "memo.txt" and there["folder_id"] == folder["id"]
    assert (await client.get(f"/files/{there['id']}")).content == b"Some text."


async def test_s3_uploads_are_sealed_and_downloadable(client, monkeypatch):
    objects = {}

    class Bucket:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            assert Bucket == "test-bucket"
            assert ContentType == "application/octet-stream"
            objects[Key] = Body

        def get_object(self, *, Bucket, Key):
            assert Bucket == "test-bucket"
            return {"Body": io.BytesIO(objects[Key])}

        def delete_object(self, *, Bucket, Key):
            assert Bucket == "test-bucket"
            objects.pop(Key, None)

    settings = get_settings()
    monkeypatch.setattr(settings, "s3_bucket", "test-bucket")
    monkeypatch.setattr(settings, "document_encryption_key",
                        base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setattr(store, "_s3", Bucket)

    data = b"Synthetic S3 document"
    result = await client.post("/files", files={"file": ("upload.txt", data)})
    assert result.status_code == 201, result.text
    file_id = result.json()["id"]
    key, = objects
    assert key.startswith("sealed/") and key.endswith(f"/{file_id}/payload")
    assert data not in objects[key]
    assert not list(settings.storage_dir.iterdir())
    assert (await client.get(f"/files/{file_id}")).content == data
    assert (await client.delete(f"/files/{file_id}")).status_code == 204
    assert not objects
