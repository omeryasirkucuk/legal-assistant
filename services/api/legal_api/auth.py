"""Password hashing, signed session cookies and the current-user dependency.

Passwords use scrypt from the standard library (no native build step on any OS). Sessions
are signed, time-limited cookies tied to the account’s current session version.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.config import get_settings
from legal_api.db.app_models import User
from legal_api.db.session import get_session

COOKIE = "session"
MAX_AGE_S = 60 * 60 * 24 * 30
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt + digest).decode()


def check_password(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored.removeprefix("scrypt$"))
    salt, digest = raw[:16], raw[16:]
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT), digest)


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def session_token(user_id: uuid.UUID, version: int = 0) -> str:
    # Keep version-zero cookies compatible with existing sessions and rolling deploys.
    payload = f"{user_id}:{version}" if version else str(user_id)
    return _signer().dumps(payload)


async def current_user(
    db: Annotated[AsyncSession, Depends(get_session)],
    session: Annotated[str | None, Cookie()] = None,
) -> User:
    if session:
        try:
            payload = _signer().loads(session, max_age=MAX_AGE_S)
            identifier, separator, value = payload.partition(":")
            user_id = uuid.UUID(identifier)
            version = int(value) if separator else 0
        except (BadSignature, ValueError, AttributeError):
            pass
        else:
            user = await db.get(User, user_id)
            if user is not None and user.session_version == version:
                return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED)


def require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator access required")


CurrentUser = Annotated[User, Depends(current_user)]
DB = Annotated[AsyncSession, Depends(get_session)]
