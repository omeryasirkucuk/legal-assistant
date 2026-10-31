"""Answer runs that live on the server, independent of the browser connection.

An answer used to be produced inside the HTTP response: when the lawyer switched to another
chat the browser closed the connection, the generator was cancelled, and the answer was lost.
Now the answer runs as a background task that records every event; any number of
connections can follow it, from the start, and the result is saved whether or not anyone is
watching. One run per chat at a time. State is in process memory: a single API process is
assumed (several workers would need a shared store).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

KEEP_FINISHED_S = 600       # a finished run can still be replayed for this long


@dataclass
class Run:
    chat_id: uuid.UUID
    events: list[tuple[str, dict]] = field(default_factory=list)
    done: bool = False
    finished_at: float | None = None
    task: asyncio.Task | None = None
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def emit(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))
        self._changed.set()

    def finish(self) -> None:
        self.done = True
        self.finished_at = time.monotonic()
        self._changed.set()

    async def follow(self) -> AsyncIterator[tuple[str, dict]]:
        """Every event so far, then new ones as they come, until the run ends."""
        sent = 0
        while True:
            while sent < len(self.events):
                yield self.events[sent]
                sent += 1
            if self.done:
                return
            self._changed.clear()
            if sent < len(self.events) or self.done:
                continue
            await self._changed.wait()


_runs: dict[uuid.UUID, Run] = {}


def _forget_old() -> None:
    now = time.monotonic()
    for chat_id, run in list(_runs.items()):
        if run.done and run.finished_at and now - run.finished_at > KEEP_FINISHED_S:
            del _runs[chat_id]


def active(chat_id: uuid.UUID) -> Run | None:
    _forget_old()
    run = _runs.get(chat_id)
    return run if run and not run.done else None


def latest(chat_id: uuid.UUID) -> Run | None:
    _forget_old()
    return _runs.get(chat_id)


def start(chat_id: uuid.UUID,
          work: Callable[[Run], Coroutine[Any, Any, None]]) -> Run:
    """Run `work(run)` in the background; it emits events on the run."""
    run = Run(chat_id)
    _runs[chat_id] = run

    async def main() -> None:
        try:
            await work(run)
        except asyncio.CancelledError:
            run.emit("cancelled", {})
        except Exception:
            logger.exception("answer run failed for chat %s", chat_id)
            run.emit("error", {})
        finally:
            run.finish()

    run.task = asyncio.create_task(main())
    return run


async def cancel(chat_id: uuid.UUID, wait_s: float = 5.0) -> bool:
    """Cancel the chat's run and wait briefly for it to finish its cleanup."""
    run = active(chat_id)
    if run is None or run.task is None:
        return False
    run.task.cancel()
    await asyncio.wait({run.task}, timeout=wait_s)
    return True
