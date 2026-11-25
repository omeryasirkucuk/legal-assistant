"""Authenticated encryption of file bytes, bound to the owning account and file UUID."""

from __future__ import annotations

import base64
import binascii
import os
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"LEGAL-FILE\x01"
NONCE_SIZE = 12


class FileProtectionError(RuntimeError):
    """The application's file protection could not decrypt or verify the payload."""


def document_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        key = b""
    if len(key) != 32:
        raise FileProtectionError("DOCUMENT_ENCRYPTION_KEY must encode 32 random bytes")
    return key


def _binding(user_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    return VERSION + user_id.bytes + file_id.bytes


def seal(data: bytes, key: bytes, user_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    return VERSION + nonce + AESGCM(key).encrypt(nonce, data, _binding(user_id, file_id))


def unseal(data: bytes, key: bytes, user_id: uuid.UUID, file_id: uuid.UUID) -> bytes:
    if not data.startswith(VERSION) or len(data) < len(VERSION) + NONCE_SIZE + 16:
        raise FileProtectionError("invalid encrypted file envelope")
    start, end = len(VERSION), len(VERSION) + NONCE_SIZE
    try:
        return AESGCM(key).decrypt(data[start:end], data[end:], _binding(user_id, file_id))
    except InvalidTag:
        raise FileProtectionError("encrypted file could not be authenticated") from None
