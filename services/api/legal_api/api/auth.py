"""Register, log in, log out, who am I."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

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
from legal_api.db.app_models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=200)
    invite_code: str = Field(default="", max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool


def _out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, name=user.name, is_admin=user.is_admin)


def _set_cookie(response: Response, user: User) -> None:
    response.set_cookie(COOKIE, session_token(user.id), max_age=MAX_AGE_S, httponly=True,
                        samesite="lax", secure=get_settings().cookie_secure)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: Registration, response: Response, db: DB) -> UserOut:
    expected = get_settings().invite_code
    if not expected or not hmac.compare_digest(body.invite_code.strip(), expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid invite code")
    email = body.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    is_admin = not bool(await db.scalar(select(func.count()).select_from(User)))
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return _out(user)
