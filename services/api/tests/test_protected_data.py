import base64
import uuid

import httpx
import pytest

from legal_api import decisions, llm
from legal_api.config import Settings
from legal_api.privacy.file_crypto import FileProtectionError, seal, unseal
from legal_api.privacy.policy import validate
from legal_api.sources import gateway


def _settings(**overrides):
    values = {
        "data_mode": "protected",
        "secret_key": "synthetic-secret-at-least-32-characters",
        "cookie_secure": True,
        "document_encryption_key": base64.urlsafe_b64encode(bytes(range(32))).decode(),
        "private_model_base_url": "http://127.0.0.1:19001/v1",
        "private_model_api_key": "private-token",
    }
    return Settings(_env_file=None, **(values | overrides))


def test_encrypted_files_are_bound_to_their_account_and_identifier():
    key = bytes(range(32))
    file_id, user_id = uuid.uuid4(), uuid.uuid4()
    encrypted = seal(b"Synthetic document", key, user_id, file_id)
    assert unseal(encrypted, key, user_id, file_id) == b"Synthetic document"
    with pytest.raises(FileProtectionError):
        unseal(encrypted, key, uuid.uuid4(), file_id)
    with pytest.raises(FileProtectionError):
        unseal(encrypted[:-1] + bytes([encrypted[-1] ^ 1]), key, user_id, file_id)


@pytest.mark.parametrize("overrides", [
    {"document_encryption_key": "invalid"},
    {"cookie_secure": False},
    {"private_model_base_url": "http://example.com/v1"},
    {"private_model_base_url": "https://name:password@example.com/v1"},
])
def test_bad_protected_configuration_is_rejected(overrides):
    with pytest.raises(RuntimeError):
        validate(_settings(**overrides))


async def test_protected_mode_pins_inference_and_blocks_public_source_requests(monkeypatch):
    settings = _settings(anthropic_via_openrouter=True, decision_api_key="legacy-secret")
    validate(settings)
    for module in [llm, decisions, gateway]:
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    token = llm.set_runtime_config(llm.RuntimeConfig("openai_compatible", "https://example.com/v1",
                                                     "legacy", "a", "b", "c", "d"))
    try:
        assert llm.openai_for("write") and llm.routed("write") is None
        assert not decisions.enabled()
        async with llm.openai_client() as client:
            assert str(client.base_url) == "http://127.0.0.1:19001/v1/"
            assert client.headers["authorization"] == "Bearer private-token"
            assert not client.trust_env
        with pytest.raises(RuntimeError):
            decisions.client()
        source = gateway.Gateway(transport=httpx.MockTransport(
            lambda _request: pytest.fail("protected request reached its transport")))
        try:
            with pytest.raises(gateway.SourceError):
                await source.json("POST", "https://example.com/search", source="test")
        finally:
            await source.aclose()
    finally:
        llm.reset_runtime_config(token)
