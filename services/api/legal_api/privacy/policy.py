"""Deployment configuration for a private, operator-managed inference boundary."""

from urllib.parse import urlsplit

from legal_api.config import Settings
from legal_api.privacy.file_crypto import document_key


def validate(settings: Settings) -> None:
    if settings.document_encryption_key or settings.protected_data:
        document_key(settings.document_encryption_key)
    if not settings.protected_data:
        return
    if len(settings.secret_key) < 32 or not settings.cookie_secure:
        raise RuntimeError("protected mode requires a random SECRET_KEY and COOKIE_SECURE=true")
    try:
        target = urlsplit(settings.private_model_base_url)
        _ = target.port
    except ValueError:
        raise RuntimeError("PRIVATE_MODEL_BASE_URL is invalid") from None
    loopback = target.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not target.hostname or target.username is not None or target.password is not None
            or target.query or target.fragment or any(c.isspace() for c in target.geturl())
            or not (target.scheme == "https" or target.scheme == "http" and loopback)):
        raise RuntimeError("PRIVATE_MODEL_BASE_URL requires HTTPS or loopback HTTP")
