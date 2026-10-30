import asyncio
import uuid

from legal_api.chat import runs


async def _collect(run: runs.Run) -> list[str]:
    return [event for event, _ in [e async for e in run.follow()]]


def test_a_late_follower_gets_every_event_and_the_run_survives_without_followers():
    async def scenario():
        gate = asyncio.Event()

        async def work(run: runs.Run) -> None:
            run.emit("step", {})
            await gate.wait()
            run.emit("final", {})

        run = runs.start(uuid.uuid4(), work)
        await asyncio.sleep(0)
        first = asyncio.create_task(_collect(run))
        await asyncio.sleep(0)
        first.cancel()                       # the browser switched chats
        gate.set()
        await run.task
        return await _collect(run)           # the browser came back

    assert asyncio.run(scenario()) == ["step", "final"]


def test_cancel_stops_the_run():
    async def scenario():
        async def work(run: runs.Run) -> None:
            run.emit("step", {})
            await asyncio.sleep(10)

        chat_id = uuid.uuid4()
        run = runs.start(chat_id, work)
        await asyncio.sleep(0)
        assert runs.cancel(chat_id)
        await run.task
        return [e for e, _ in run.events], runs.active(chat_id)

    events, active = asyncio.run(scenario())
    assert events == ["step", "cancelled"] and active is None
