"""One chat turn: decide what the message asks for (route.py) and answer it that way."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import date, datetime
from time import monotonic
from xml.sax.saxutils import escape

from legal_api import llm
from legal_api.agent.answer import Event, step_event
from legal_api.agent.pipeline import answer_events, direct_events, rewrite_events
from legal_api.agent.power import POWERS, Power
from legal_api.agent.route import direct_intent, route
from legal_api.agent.sources import Source
from legal_api.drafting.brief import StyleBook
from legal_api.files.context import Attachment
from legal_api.locale import chat_turns
from legal_api.matters.agenda import Agenda
from legal_api.retrieval.statutes import article_request
from legal_api.workspace.session import Context


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
                      attachments: list[Attachment] | None = None,
                      agenda: Agenda | None = None,
                      usage: llm.Usage | None = None,
                      workspace: Context | None = None,
                      style_loader: Callable[[], Awaitable[StyleBook]] | None = None,
                      *, today: date | None = None
                      ) -> AsyncIterator[Event]:
    started = monotonic()
    usage = usage if usage is not None else llm.Usage()
    just_asked = bool(previous and (previous.answer or {}).get("asked"))
    yield step_event("understand")
    kind = None if attachments else direct_intent(message)
    exact = kind is None and not (attachments or just_asked) and article_request(message)
    if kind is None:
        if exact or attachments or (previous and (previous.answer or {}).get("task") == "workspace"):
            kind = "followup" if just_asked else "new"
        else:
            kind = await route(message, previous.question if previous else None,
                               previous.short if previous else None, usage)
    if kind in chat_turns():
        yield Event("route", {"kind": "direct"})
        yield step_event("understand", "done")
        async for event in direct_events(message, kind, usage, result, started):
            yield event
        return
    just_asked = just_asked and kind == "followup"
    if kind == "reformat" and previous and previous.short:
        sources = [Source(e, e.text) for e in previous.evidence]
        events = rewrite_events(message, previous.question, previous.short, sources, usage,
                                result, today=today)
    elif just_asked and previous:
        # The reply completes the request asked about: both are what the petition is written
        # from (the writer sees only the message; a date given in the request was lost).
        events = answer_events(followup_request(previous.question, message), history, result,
                               usage=usage, style=style, power=power, attachments=attachments,
                               just_asked=True, agenda=agenda, workspace=workspace,
                               style_loader=style_loader, today=today)
    elif kind == "followup" and previous:
        events = answer_events(message, history, result,
                               search_text=followup_request(previous.question, message), usage=usage,
                               style=style, power=power, attachments=attachments,
                               just_asked=just_asked, agenda=agenda, workspace=workspace,
                               style_loader=style_loader, today=today)
    else:
        events = answer_events(message, [] if exact else history, result, usage=usage, style=style,
                               power=power, attachments=attachments, just_asked=just_asked,
                               agenda=agenda, workspace=workspace,
                               style_loader=style_loader, today=today)
    yield Event("route", {"kind": kind})
    yield step_event("understand", "done")
    async with aclosing(events):
        async for event in events:
            yield event


def followup_request(previous_question: str, message: str) -> str:
    return (f"<previous_question>{escape(previous_question)}</previous_question>\n"
            f"<current_request>{escape(message)}</current_request>")
