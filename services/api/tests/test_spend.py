import uuid

from sqlalchemy import delete

from legal_api import llm
from legal_api.chat.service import spent_today
from legal_api.db.app_models import User
from legal_api.db.session import get_sessionmaker
from legal_api.spend import record_spend


class _Usage(llm.Usage):
    def __init__(self, cost: float):
        super().__init__()
        self._cost = cost

    @property
    def cost_usd(self) -> float:
        return self._cost


async def test_spend_outside_answers_counts_toward_the_daily_budget():
    async with get_sessionmaker()() as db:
        user = User(email=f"spend-{uuid.uuid4().hex[:8]}@example.com", name="S", password_hash="x")
        db.add(user)
        await db.commit()
        try:
            assert await spent_today(db, user.id) == 0
            await record_spend(db, user.id, "draft_adjust", _Usage(0.012))
            await record_spend(db, user.id, "sample_read", _Usage(0.0))   # nothing spent, no row
            await db.commit()
            assert round(await spent_today(db, user.id), 4) == 0.012
        finally:
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
