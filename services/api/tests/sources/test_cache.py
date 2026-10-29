import asyncio

import pytest

from legal_api.sources.cache import TTLCache


async def test_concurrent_requests_share_one_upstream_call():
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "v"

    cache = TTLCache()
    assert await asyncio.gather(*(cache.get("k", load) for _ in range(5))) == ["v"] * 5
    assert await cache.get("k", load) == "v"
    assert calls == 1


async def test_failures_are_not_cached():
    cache = TTLCache()

    async def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        await cache.get("k", boom)

    async def ok():
        return 1

    assert await cache.get("k", ok) == 1
