"""One chat turn: decide what the message asks for (route.py) and answer it that way."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from legal_api import llm
from legal_api.agent.answer import Event, answer_events, step_event
from legal_api.agent.reformat import can_reformat, reformat_events
from legal_api.agent.route import route


@dataclass(frozen=True)
class EvidenceCopy:
    """A source of the previous answer, detached from the database session."""
    key: str
    kind: str
    citation: str
    url: str
    text: str
    fetched_at: datetime


@dataclass
class Previous:
    """The last answered turn of the chat."""
    question: str
    answer: dict | None          # messages.meta.answer
    short: str                   # the short answer as the lawyer read it
    evidence: list[EvidenceCopy] = field(default_factory=list)


async def turn_events(message: str, history: list[dict], previous: Previous | None,
                      result: dict) -> AsyncIterator[Event]:
    usage = llm.Usage()
    yield step_event("understand")
    kind = await route(message, previous.question if previous else None,
                       previous.short if previous else None, usage)
    if kind == "reformat" and previous and can_reformat(previous.answer):
        events = reformat_events(message, previous.question, previous.answer,
                                 previous.evidence, usage, result)
    elif kind == "followup" and previous:
        events = answer_events(message, history, result,
                               search_text=f"{previous.question}\n{message}", usage=usage)
    else:
        events = answer_events(message, history, result, usage=usage)
    yield Event("route", {"kind": kind})
    yield step_event("understand", "done")
    async for event in events:
        yield event
