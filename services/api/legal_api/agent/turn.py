"""One chat turn: decide what the message asks for (route.py) and answer it that way."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from legal_api import llm
from legal_api.agent.answer import Event, step_event
from legal_api.agent.pipeline import answer_events, rewrite_events
from legal_api.agent.power import POWERS, Power
from legal_api.agent.route import route
from legal_api.agent.sources import Source
from legal_api.drafting.brief import StyleBook
from legal_api.files.context import Attachment


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
                      result: dict, style: StyleBook | None = None, power: Power = POWERS["balanced"],
                      attachments: list[Attachment] | None = None) -> AsyncIterator[Event]:
    usage = llm.Usage()
    just_asked = bool(previous and (previous.answer or {}).get("asked"))
    yield step_event("understand")
    # A reply to a question turn carries the facts for the request asked about; a message with
    # attachments brings new material: it is answered afresh, not reformatted.
    if just_asked:
        kind = "followup"
    elif attachments:
        kind = "new"
    else:
        kind = await route(message, previous.question if previous else None,
                           previous.short if previous else None, usage)
    if kind == "reformat" and previous and previous.short:
        sources = [Source(e, e.text) for e in previous.evidence]
        events = rewrite_events(message, previous.question, previous.short, sources, usage,
                                result)
    elif just_asked and previous:
        # The reply completes the request asked about: both are what the petition is written
        # from (the writer sees only the message; a date given in the request was lost).
        events = answer_events(f"{previous.question}\n\n{message}", history, result,
                               usage=usage, style=style, power=power, attachments=attachments,
                               just_asked=True)
    elif kind == "followup" and previous:
        events = answer_events(message, history, result,
                               search_text=f"{previous.question}\n{message}", usage=usage,
                               style=style, power=power, attachments=attachments,
                               just_asked=just_asked)
    else:
        events = answer_events(message, history, result, usage=usage, style=style,
                               power=power, attachments=attachments, just_asked=just_asked)
    yield Event("route", {"kind": kind})
    yield step_event("understand", "done")
    async for event in events:
        yield event
