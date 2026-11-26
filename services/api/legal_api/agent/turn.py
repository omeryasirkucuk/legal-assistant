"""One chat turn: decide what the message asks for (route.py) and answer it that way."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic

from legal_api import llm
from legal_api.agent.answer import Event, step_event
from legal_api.agent.atoms import Segment
from legal_api.agent.pipeline import WrittenResult, answer_events, rewrite_events
from legal_api.agent.power import POWERS, Power
from legal_api.agent.route import direct_intent, route
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.agent.write import Written
from legal_api.drafting.brief import StyleBook
from legal_api.files.context import Attachment
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import chat_turns
from legal_api.matters.agenda import Agenda
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
                      *, explicit_files: bool | None = None) -> AsyncIterator[Event]:
    started = monotonic()
    usage = usage if usage is not None else llm.Usage()
    just_asked = bool(previous and (previous.answer or {}).get("asked"))
    yield step_event("understand")
    uploaded = bool(attachments) if explicit_files is None else explicit_files
    workspace_reply = previous is not None and (previous.answer or {}).get("task") == "workspace"
    kind = None if uploaded else direct_intent(message)
    if kind is None and uploaded:
        kind = "followup" if just_asked else "new"
    elif kind is None:
        kind = await route(message, previous.question if previous else None,
                           previous.short if previous else None, usage)
    if kind in chat_turns():
        reply = chat_turns()[kind]["reply"]
        res = WrittenResult(message, Understanding(task="direct"),
                            Written([Segment(reply)], reply, []), EvidenceLedger(), usage,
                            {"total_s": round(monotonic() - started, 1)}, {"route": "direct"})
        result["result"] = res
        yield Event("route", {"kind": "direct"})
        yield step_event("understand", "done")
        yield Event("delta", {"text": reply})
        yield Event("final", {"text": reply, "cost_usd": round(usage.cost_usd, 4),
                              "timings": res.timings})
        return
    if workspace_reply and kind in {"reformat", "followup"}:
        kind = "contextual"
    just_asked = just_asked and kind in {"followup", "contextual"}
    if kind == "reformat" and previous and previous.short:
        sources = [Source(e, e.text) for e in previous.evidence]
        events = rewrite_events(message, previous.question, previous.short, sources, usage,
                                result)
    elif just_asked and previous:
        # The reply completes the request asked about: both are what the petition is written
        # from (the writer sees only the message; a date given in the request was lost).
        events = answer_events(f"{previous.question}\n\n{message}", history, result,
                               usage=usage, style=style, power=power, attachments=attachments,
                               just_asked=True, agenda=agenda, workspace=workspace)
    elif kind == "followup" and previous:
        context = history or [{"role": "user", "content": previous.question},
                              {"role": "assistant", "content": previous.short}]
        events = answer_events(message, context, result,
                               search_text=(f"<previous_question>{previous.question}</previous_question>\n"
                                            f"<current_request>{message}</current_request>"), usage=usage,
                               style=style, power=power, attachments=attachments,
                               just_asked=just_asked, agenda=agenda, workspace=workspace)
    else:
        context = history if uploaded or kind == "contextual" else []
        events = answer_events(message, context, result, usage=usage, style=style,
                               power=power, attachments=attachments, just_asked=just_asked,
                               agenda=agenda, workspace=workspace)
    yield Event("route", {"kind": kind})
    yield step_event("understand", "done")
    async for event in events:
        yield event
    if "result" in result and kind == "new" and not uploaded:
        result["result"].trace["starts_topic"] = True
