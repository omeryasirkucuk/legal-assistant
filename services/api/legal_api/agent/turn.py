"""One chat turn: decide what the message asks for (route.py) and answer it that way."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
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
from legal_api.files.context import IMAGE_TYPES, MAX_IMAGE_BYTES, Attachment
from legal_api.files.store import read as read_file
from legal_api.grounding.evidence import EvidenceLedger
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


def case_turns(previous: Previous | None, history: list[dict]) -> list[str]:
    """Bounded verbatim user context. Keep the opening request and newest distinct turns."""
    stored = (previous.answer or {}).get("case_turns", []) if previous else []
    candidates = [*stored, *(t["content"] for t in history if t["role"] == "user")]
    if previous:
        candidates.append(previous.question)
    return _bounded_turns(candidates)


def _bounded_turns(messages: list[str]) -> list[str]:
    turns: list[str] = []
    for message in messages:
        if not isinstance(message, str) or not message.strip():
            continue
        excerpt = message if len(message) <= 1400 else message[:900] + " […] " + message[-490:]
        if excerpt in turns:
            turns.remove(excerpt)
        turns.append(excerpt)
    return turns[:1] + turns[-9:] if len(turns) > 10 else turns


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
    earlier = case_turns(previous, history)
    if kind is None and not (uploaded or attachments) and article_request(message):
        kind = "new"
    if kind is None:
        kind = await route(message, previous.question if previous else None,
                           previous.short if previous else None, usage, earlier,
                           [a.name for a in attachments or []] if uploaded else [])
    if uploaded and (kind in chat_turns() or kind == "reformat"):
        kind = "contextual"
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
    continuing = kind in {"followup", "contextual", "reformat"}
    active = earlier if continuing else []
    if continuing and previous and not history:
        history = [{"role": "user", "content": previous.question},
                   {"role": "assistant", "content": previous.short}]
    current_ids = [a.file_id for a in attachments or [] if a.file_id]
    remembered = (previous.answer or {}).get("case_file_ids", []) if continuing and previous else []
    case_files = list(dict.fromkeys([*remembered, *current_ids]))[-5:]
    if remembered and workspace and kind != "reformat":
        attachments = list(attachments or [])
        # Resolve only files still accessible to this user through the active chat or matter.
        by_id = {str(f.id): f for f in workspace.files}
        for file_id in case_files:
            f = by_id.get(file_id)
            if f is None or file_id in current_ids:
                continue
            image = None
            if f.media_type in IMAGE_TYPES and f.size <= MAX_IMAGE_BYTES:
                image = await asyncio.to_thread(read_file, f)
            if image or f.text:
                attachments.append(Attachment(f.name, f.media_type, f.text, image, file_id))
    recent = {t["content"] for t in history if t["role"] == "user"}
    older = [text for text in active if text not in recent]
    if older:
        history = [{"role": "user", "content": text} for text in older] + history
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
    else:
        request = None
        if continuing and previous:
            notes = json.dumps(active[:-1], ensure_ascii=False)
            request = (f"<earlier_user_messages>{notes}</earlier_user_messages>\n"
                       f"<previous_question>{previous.question}</previous_question>\n"
                       f"<current_request>{message}</current_request>")
        events = answer_events(message, history if continuing else [], result, search_text=request,
                               usage=usage, style=style, power=power, attachments=attachments,
                               just_asked=just_asked, agenda=agenda, workspace=workspace)
    yield Event("route", {"kind": kind})
    yield step_event("understand", "done")
    async with aclosing(events):
        async for event in events:
            yield event
    if "result" in result:
        result["result"].case_file_ids = case_files
        result["result"].case_turns = _bounded_turns([*active, message])
    if "result" in result and kind == "new":
        result["result"].trace["starts_topic"] = True
