"""Model spend outside chat answers (a petition rewritten with a button, a sample petition
read, a style learnt from edits), recorded so the daily budget counts all of a lawyer's use
(chat/service.spent_today)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from legal_api import llm
from legal_api.db.app_models import LlmSpend


async def record_spend(db: AsyncSession, user_id: uuid.UUID, purpose: str,
                       usage: llm.Usage) -> None:
    """Added to the session; committed with the caller's next commit."""
    if usage.cost_usd > 0:
        db.add(LlmSpend(user_id=user_id, purpose=purpose, cost_usd=round(usage.cost_usd, 6)))
