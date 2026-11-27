import asyncio
from types import SimpleNamespace

from legal_api.agent import case_law


async def test_supplemental_lookup_keeps_decisions_fetched_before_timeout(monkeypatch):
    class Source:
        async def search(self, query, *, size):
            return 2, ["first", "second"]

        async def fetch(self, ref):
            if ref == "second":
                await asyncio.Future()
            return SimpleNamespace(text="First decision")

    monkeypatch.setattr(case_law, "SUPPLEMENTAL_LIVE_BUDGET_S", 0)
    monkeypatch.setattr(case_law, "_closest_passage", lambda text, _ask: text)

    result = await case_law._live(Source(), "test query", "question", supplemental=True)

    assert [decision.passage for decision in result] == ["First decision"]
