"""Administrator-managed shared LLM connection settings."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from legal_api import llm
from legal_api.auth import DB, CurrentUser, require_admin
from legal_api.config import get_settings
from legal_api.db.app_models import LLMConnectionSettings
from legal_api.privacy.credentials import encrypt_credential
from legal_api.privacy.llm_settings import runtime_config

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMSettingsUpdate(BaseModel):
    base_url: str = Field(min_length=8, max_length=1000)
    api_key: str | None = Field(default=None, max_length=8000)
    clear_api_key: bool = False
    model_main: str = Field(min_length=1, max_length=200)
    model_draft: str = Field(min_length=1, max_length=200)
    model_cheap: str = Field(min_length=1, max_length=200)
    model_judge: str = Field(min_length=1, max_length=200)
    model_write: str | None = Field(default=None, min_length=1, max_length=200)


def _encrypt(value: str) -> str:
    try:
        return encrypt_credential(value)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _default_openai_connection() -> tuple[str, str]:
    s = get_settings()
    if all(llm.routed(role) for role in ("main", "draft", "cheap", "judge", "write")):
        return s.decision_base_url.rstrip("/") + "/v1", s.decision_api_key
    return s.openai_base_url, s.openai_api_key


def _out(row: LLMConnectionSettings | None) -> dict:
    s = get_settings()
    managed = s.protected_data
    base_url, api_key = _default_openai_connection()
    config = llm.RuntimeConfig(
        "openai_compatible", row.base_url, "", row.model_main, row.model_draft,
        row.model_cheap, row.model_judge, row.model_write,
    ) if row else None
    token = llm.set_runtime_config(config)
    try:
        effective = {
            "model_main": llm.routed("main") or llm.model_for("main"),
            "model_draft": llm.routed("draft") or llm.model_for("draft"),
            "model_cheap": llm.routed("cheap") or llm.model_for("cheap"),
            "model_judge": llm.routed("judge") or llm.model_for("judge"),
            "model_write": llm.routed("write") or llm.model_for("write"),
        }
    finally:
        llm.reset_runtime_config(token)
    return {
        "provider": "openai_compatible",
        "operator_managed": managed,
        "is_saved": managed or row is not None,
        "base_url": "" if managed else row.base_url if row else base_url,
        "api_key_configured": bool(
            s.private_model_api_key if managed else row.api_key_encrypted if row else api_key
        ),
        **effective,
    }


@router.get("/llm")
async def get_llm_settings(user: CurrentUser, db: DB) -> dict:
    require_admin(user)
    return _out(await db.get(LLMConnectionSettings, 1))


@router.put("/llm")
async def update_llm_settings(body: LLMSettingsUpdate, user: CurrentUser, db: DB) -> dict:
    require_admin(user)
    if get_settings().protected_data:
        raise HTTPException(status.HTTP_409_CONFLICT, "model is managed by the operator")
    base_url = body.base_url.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "base_url must be an http(s) URL without embedded credentials")

    default_url, default_key = _default_openai_connection()
    row = await db.get(LLMConnectionSettings, 1)
    first_save = row is None
    if row is None:
        row = LLMConnectionSettings(id=1)
        db.add(row)
    elif row.base_url != base_url:
        row.api_key_encrypted = None

    row.base_url = base_url
    row.model_main = body.model_main.strip()
    row.model_draft = body.model_draft.strip()
    row.model_cheap = body.model_cheap.strip()
    row.model_judge = body.model_judge.strip()

    if body.model_write is not None:
        row.model_write = body.model_write.strip()

    if body.clear_api_key:
        row.api_key_encrypted = None
    elif body.api_key is not None and body.api_key.strip():
        row.api_key_encrypted = _encrypt(body.api_key.strip())
    elif first_save and default_key and base_url == default_url.rstrip("/"):
        row.api_key_encrypted = _encrypt(default_key)

    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.get("/llm/models")
async def list_llm_models(user: CurrentUser, db: DB) -> list[dict]:
    require_admin(user)
    if get_settings().protected_data:
        raise HTTPException(status.HTTP_409_CONFLICT, "model is managed by the operator")
    row = await db.get(LLMConnectionSettings, 1)
    config = runtime_config(row)
    base_url, api_key = (config.base_url, config.api_key) if config else _default_openai_connection()
    headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers,
                                     timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.get("models")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"model list endpoint returned HTTP {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "could not load models; check the API URL and key") from exc

    entries = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "model list response has an unsupported format")
    models: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id") or entry.get("model")
        if isinstance(model_id, str) and model_id.strip():
            models[model_id] = {"id": model_id, "name": entry.get("name") or model_id}
    return sorted(models.values(), key=lambda model: (str(model["name"]).casefold(), model["id"]))


@router.post("/llm/test")
async def test_llm_connection(user: CurrentUser, db: DB) -> dict:
    require_admin(user)
    row = await db.get(LLMConnectionSettings, 1)
    token = llm.set_runtime_config(runtime_config(row))
    try:
        result = await llm.create(
            "main", llm.Usage(), "connection_test", max_tokens=16,
            system="Reply with exactly OK.",
            messages=[{"role": "user", "content": "Connection test"}],
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"model endpoint returned HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "could not reach the model; check the API URL, key and model ID") from exc
    finally:
        llm.reset_runtime_config(token)
    if not any(block.text.strip() for block in result.content if block.type == "text"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "model endpoint returned an empty response")
    return {"ok": True, "model": result.model}
