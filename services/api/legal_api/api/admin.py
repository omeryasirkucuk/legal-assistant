"""Account and model-spend administration."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field, StrictBool
from sqlalchemy import func, select, text

from legal_api.auth import DB, CurrentUser, require_admin
from legal_api.config import get_settings
from legal_api.db.app_models import LlmSpend, RegistrationInvite, User
from legal_api.privacy.credentials import decrypt_credential, encrypt_credential
from legal_api.spend import start_of_utc_day, start_of_utc_month

router = APIRouter(prefix="/admin", tags=["admin"])


class AccountRole(BaseModel):
    is_admin: StrictBool


class AccountBudget(BaseModel):
    daily_budget_usd: float | None = Field(ge=0, strict=True, allow_inf_nan=False)
    monthly_budget_usd: float | None = Field(ge=0, strict=True, allow_inf_nan=False)


class AccountSummary(AccountRole, AccountBudget):
    id: uuid.UUID
    name: str
    email: str
    today_cost_usd: float
    monthly_cost_usd: float
    total_cost_usd: float
    default_daily_budget_usd: float


class InviteRecipient(BaseModel):
    email: EmailStr


class InviteCode(InviteRecipient):
    id: str
    code: str | None
    status: Literal["active", "used", "expired"]
    expires_at: datetime | None
    used_at: datetime | None


def _invite_out(invite: RegistrationInvite, now: datetime) -> InviteCode:
    if invite.used_at is not None:
        state = "used"
    elif invite.expires_at is None or invite.expires_at <= now:
        state = "expired"
    else:
        state = "active"
    return InviteCode(
        id=invite.code_hash, email=invite.email, status=state,
        code=decrypt_credential(invite.code_encrypted) if invite.code_encrypted else None,
        expires_at=invite.expires_at, used_at=invite.used_at,
    )


@router.get("/invites")
async def list_invites(response: Response, user: CurrentUser, db: DB) -> list[InviteCode]:
    require_admin(user)
    invites = await db.scalars(select(RegistrationInvite).order_by(
        RegistrationInvite.expires_at.desc().nulls_last(), RegistrationInvite.code_hash,
    ))
    now = datetime.now(UTC)
    response.headers["Cache-Control"] = "no-store"
    return [_invite_out(invite, now) for invite in invites]


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteRecipient, response: Response, user: CurrentUser, db: DB) -> InviteCode:
    require_admin(user)
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    code = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    try:
        encrypted = encrypt_credential(code)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    invite = RegistrationInvite(
        code_hash=sha256(code.encode()).hexdigest(), email=email, code_encrypted=encrypted,
        expires_at=now + timedelta(hours=24),
    )
    db.add(invite)
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return _invite_out(invite, now)


@router.get("/users", response_model=list[AccountSummary])
async def users(user: CurrentUser, db: DB):
    require_admin(user)
    today = start_of_utc_day()
    spend = (
        select(
            LlmSpend.user_id,
            func.sum(LlmSpend.cost_usd)
            .filter(LlmSpend.created_at >= today).label("today"),
            func.sum(LlmSpend.cost_usd)
            .filter(LlmSpend.created_at >= start_of_utc_month(today)).label("monthly"),
            func.sum(LlmSpend.cost_usd).label("total"),
        ).group_by(LlmSpend.user_id).subquery()
    )
    rows = await db.execute(
        select(
            User.id, User.name, User.email, User.is_admin, User.daily_budget_usd, User.monthly_budget_usd,
            func.coalesce(spend.c.today, 0.0).label("today_cost_usd"),
            func.coalesce(spend.c.monthly, 0.0).label("monthly_cost_usd"),
            func.coalesce(spend.c.total, 0.0).label("total_cost_usd"),
        ).outerjoin(spend, spend.c.user_id == User.id)
        .order_by(User.created_at, User.id)
    )
    return [
        {**row, "default_daily_budget_usd": get_settings().daily_user_budget_usd}
        for row in rows.mappings()
    ]


@router.patch("/users/{user_id}/budget", response_model=AccountBudget)
async def update_budget(user_id: uuid.UUID, body: AccountBudget, user: CurrentUser, db: DB):
    require_admin(user)
    account = await db.get(User, user_id)
    if account is None:
        raise HTTPException(404, "user not found")
    account.daily_budget_usd = body.daily_budget_usd
    account.monthly_budget_usd = body.monthly_budget_usd
    await db.commit()
    return body


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
