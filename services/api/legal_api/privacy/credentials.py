"""Authenticated encryption for server-side provider credentials."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from legal_api.config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if len(secret) < 32 or secret == "dev-only-insecure-secret":
        raise RuntimeError("set SECRET_KEY to a random value of at least 32 characters")
    key = hashlib.sha256(f"legal-assistant:provider-credential:v1:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
