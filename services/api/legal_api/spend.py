"""Model spend used by the daily budget, kept independently of user content."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legal_api import llm
from legal_api.db.app_models import LlmSpend


def start_of_utc_day() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def record_spend(db: AsyncSession, user_id: uuid.UUID, purpose: str,
                       usage: llm.Usage) -> None:
    """Added to the session; committed with the caller's next commit."""
    if usage.cost_usd > 0:
        db.add(LlmSpend(user_id=user_id, purpose=purpose, cost_usd=round(usage.cost_usd, 6)))
