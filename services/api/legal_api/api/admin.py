"""Account and model-spend administration."""

import secrets
import uuid
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, StrictBool
from sqlalchemy import func, select, text

from legal_api.auth import DB, CurrentUser, require_admin
from legal_api.db.app_models import LlmSpend, RegistrationInvite, User
from legal_api.spend import start_of_utc_day

router = APIRouter(prefix="/admin", tags=["admin"])


class AccountRole(BaseModel):
    is_admin: StrictBool


class AccountSummary(AccountRole):
    id: uuid.UUID
    name: str
    email: str
    today_cost_usd: float
    total_cost_usd: float


class InviteRecipient(BaseModel):
    email: EmailStr


class InviteCode(InviteRecipient):
    code: str


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteRecipient, response: Response, user: CurrentUser, db: DB) -> InviteCode:
    require_admin(user)
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    code = secrets.token_urlsafe(32)
    db.add(RegistrationInvite(code_hash=sha256(code.encode()).hexdigest(), email=email))
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return InviteCode(email=email, code=code)


@router.get("/users", response_model=list[AccountSummary])
async def users(user: CurrentUser, db: DB):
    require_admin(user)
    spend = (
        select(
            LlmSpend.user_id,
            func.sum(LlmSpend.cost_usd)
            .filter(LlmSpend.created_at >= start_of_utc_day()).label("today"),
            func.sum(LlmSpend.cost_usd).label("total"),
        ).group_by(LlmSpend.user_id).subquery()
    )
    rows = await db.execute(
        select(
            User.id, User.name, User.email, User.is_admin,
            func.coalesce(spend.c.today, 0.0).label("today_cost_usd"),
            func.coalesce(spend.c.total, 0.0).label("total_cost_usd"),
        ).outerjoin(spend, spend.c.user_id == User.id)
        .order_by(User.created_at, User.id)
    )
    return rows.mappings().all()


@router.patch("/users/{user_id}/role", response_model=AccountRole)
async def update_role(user_id: uuid.UUID, body: AccountRole, user: CurrentUser, db: DB):
    require_admin(user)
    # Serialize role changes so two administrators cannot demote each other concurrently.
    await db.execute(text("SELECT pg_advisory_xact_lock(739128302)"))
    await db.refresh(user, attribute_names=["is_admin"])
    require_admin(user)
    account = await db.get(User, user_id)
    if account is None:
        raise HTTPException(404, "user not found")
    if account.is_admin and not body.is_admin:
        other_admin = await db.scalar(select(User.id).where(
            User.is_admin.is_(True), User.id != account.id
        ).limit(1))
        if other_admin is None:
            raise HTTPException(409, "at least one administrator is required")
    account.is_admin = body.is_admin
    await db.commit()
    return body
