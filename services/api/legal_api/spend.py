"""Model spend and account budgets, independent of user content retention."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api import llm
from legal_api.config import get_settings
from legal_api.db.app_models import LlmSpend, User


def start_of_utc_day() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_utc_month(day: datetime) -> datetime:
    return day.replace(day=1)


def daily_budget(user: User) -> float:
    if user.daily_budget_usd is not None:
        return user.daily_budget_usd
    return get_settings().daily_user_budget_usd


async def period_spend(db: AsyncSession, user_id: uuid.UUID) -> tuple[float, float]:
    today = start_of_utc_day()
    day, month = (await db.execute(
        select(
            func.sum(LlmSpend.cost_usd).filter(LlmSpend.created_at >= today),
            func.sum(LlmSpend.cost_usd),
        ).where(LlmSpend.user_id == user_id, LlmSpend.created_at >= start_of_utc_month(today))
    )).one()
    return float(day or 0), float(month or 0)


async def budget_reached(db: AsyncSession, user: User) -> str | None:
    day, month = await period_spend(db, user.id)
    # Match the ledger precision when comparing sums of floating-point entries.
    if round(day, 6) >= daily_budget(user):
        return "daily budget reached"
    if user.monthly_budget_usd is not None and round(month, 6) >= user.monthly_budget_usd:
        return "monthly budget reached"
    return None


async def guard_budget(db: AsyncSession, user: User) -> None:
    if reason := await budget_reached(db, user):
        raise HTTPException(429, reason)


async def record_spend(db: AsyncSession, user_id: uuid.UUID, purpose: str,
                       usage: llm.Usage) -> None:
    """Added to the session; committed with the caller's next commit."""
    if usage.cost_usd > 0:
        db.add(LlmSpend(user_id=user_id, purpose=purpose, cost_usd=round(usage.cost_usd, 6)))
