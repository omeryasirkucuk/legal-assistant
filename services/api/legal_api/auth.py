"""Password hashing, signed session cookies and the current-user dependency.

Passwords use scrypt from the standard library (no native build step on any OS). Sessions
are a signed, time-limited cookie holding the user id.
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


def session_token(user_id: uuid.UUID) -> str:
    return _signer().dumps(str(user_id))


async def current_user(
    db: Annotated[AsyncSession, Depends(get_session)],
    session: Annotated[str | None, Cookie()] = None,
) -> User:
    if session:
        try:
            user_id = uuid.UUID(_signer().loads(session, max_age=MAX_AGE_S))
        except (BadSignature, ValueError):
            user_id = None
        if user_id and (user := await db.get(User, user_id)):
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED)


CurrentUser = Annotated[User, Depends(current_user)]
DB = Annotated[AsyncSession, Depends(get_session)]
