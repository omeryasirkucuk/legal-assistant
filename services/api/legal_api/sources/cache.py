"""In-process TTL cache with single-flight: concurrent requests for the same key share one
upstream call. Used for legislation, which changes rarely but is requested constantly, so
repeat lookups never spend the official services' rate limit."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any

DEFAULT_TTL_S = 6 * 60 * 60


class TTLCache:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S, max_items: int = 5000):
        self._ttl = ttl_s
        self._max = max_items
        self._values: dict[Hashable, tuple[float, Any]] = {}
        self._inflight: dict[Hashable, asyncio.Future] = {}

    async def get(self, key: Hashable, load: Callable[[], Awaitable[Any]]) -> Any:
        hit = self._values.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        if key in self._inflight:
            return await asyncio.shield(self._inflight[key])
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await load()
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved; waiting callers re-raise it themselves
            raise
        finally:
            self._inflight.pop(key, None)
        if len(self._values) >= self._max:
            self._values.pop(next(iter(self._values)))
        self._values[key] = (time.monotonic() + self._ttl, value)
        future.set_result(value)
        return value

    def clear(self) -> None:
        self._values.clear()
