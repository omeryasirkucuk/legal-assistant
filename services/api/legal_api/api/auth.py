"""Register, log in, log out, change a password, and who am I."""

from __future__ import annotations

import asyncio
import hmac
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text

from legal_api.auth import (
    COOKIE,
    DB,
    MAX_AGE_S,
    CurrentUser,
    check_password,
    hash_password,
    session_token,
)
from legal_api.config import get_settings
from legal_api.db.app_models import RegistrationInvite, User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=200)
    invite_code: str = Field(default="", max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool
    protected_data: bool


def _out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name, is_admin=user.is_admin,
                   protected_data=get_settings().protected_data)


def _set_cookie(response: Response, user: User) -> None:
    response.set_cookie(COOKIE, session_token(user.id, user.session_version), max_age=MAX_AGE_S, httponly=True,
                        samesite="lax", secure=get_settings().cookie_secure)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: Registration, response: Response, db: DB) -> UserOut:
    code = body.invite_code.strip().encode()
    if not code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid invite code")

    # Serialize registrations so bootstrap and invite redemption are single-use.
    await db.execute(text("SELECT pg_advisory_xact_lock(739128301)"))
    email = body.email.lower()
    is_admin = await db.scalar(select(User.id).limit(1)) is None
    if is_admin:
        expected = get_settings().invite_code.encode()
        if not expected or not hmac.compare_digest(code, expected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid invite code")
    else:
        invite = await db.get(RegistrationInvite, sha256(code).hexdigest())
        now = datetime.now(UTC)
        if (invite is None or invite.email != email or invite.used_at is not None
                or invite.expires_at is None or invite.expires_at <= now):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid invite code")
        if await db.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
        invite.used_at = now

    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password),
                is_admin=is_admin)
    db.add(user)
    await db.commit()
    _set_cookie(response, user)
    return _out(user)


@router.post("/login")
async def login(body: Credentials, response: Response, db: DB) -> UserOut:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not check_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    _set_cookie(response, user)
    return _out(user)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, response: Response, user: CurrentUser, db: DB):
    version = user.session_version
    # Serialize changes to the same account and recheck the password and session after waiting.
    await db.refresh(user, attribute_names=["password_hash", "session_version"], with_for_update=True)
    if user.session_version != version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    if not await asyncio.to_thread(check_password, body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "incorrect current password")
    if body.current_password == body.new_password:
        raise HTTPException(status.HTTP_409_CONFLICT, "choose a different password")

    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.session_version += 1
    await db.commit()
    _set_cookie(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return _out(user)
