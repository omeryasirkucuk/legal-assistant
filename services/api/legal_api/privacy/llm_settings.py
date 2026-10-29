"""Resolve the saved application connection into a per-request runtime config."""

from legal_api.db.app_models import LLMConnectionSettings
from legal_api.llm import RuntimeConfig
from legal_api.privacy.credentials import decrypt_credential


def runtime_config(row: LLMConnectionSettings | None) -> RuntimeConfig | None:
    if row is None:
        return None
    return RuntimeConfig(
        provider="openai_compatible",
        base_url=row.base_url,
        api_key=decrypt_credential(row.api_key_encrypted) if row.api_key_encrypted else "",
        model_main=row.model_main,
        model_draft=row.model_draft,
        model_cheap=row.model_cheap,
        model_judge=row.model_judge,
    )
