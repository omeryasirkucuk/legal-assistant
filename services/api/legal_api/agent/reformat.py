"""Answer a request to present the previous answer differently, without new retrieval.

The earlier answer's cited sub-answers and sources are reused; only the short answer is
written again under the lawyer's instruction, with the same checks as a new answer
(compose.py). The new message keeps the earlier sources, so its citations stay viewable.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

from legal_api import llm
from legal_api.agent.answer import Event, message_text, plain_text, step_event
from legal_api.agent.compose import Line, compose, lines_data, short_text


@dataclass
class ReformatResult:
    """Has what chat/service.save_answer stores, like AnswerResult."""
    answer: dict
    ledger: Iterable[Any]                 # evidence rows of the earlier answer
    usage: llm.Usage
    timings: dict[str, float] = field(default_factory=dict)
    trace: dict = field(default_factory=lambda: {"route": "reformat"})

    def structure(self) -> dict:
        return self.answer

    @property
    def short(self) -> str:
        return short_text_of(self.answer)

    @property
    def text(self) -> str:
        return message_text(self.short, plain_text(self.answer))


def short_text_of(answer: dict) -> str:
    return short_text([Line(ln["branch"], ln["text"], tuple(ln["keys"]), ln["composed"])
                       for ln in answer.get("lines", [])])


def can_reformat(answer: dict | None) -> bool:
    return bool(answer and any(a["found"] for b in answer.get("branches", [])
                               for a in b["atoms"]))


async def reformat_events(instruction: str, question: str, answer: dict, evidence: list,
                          usage: llm.Usage, result: dict | None = None
                          ) -> AsyncIterator[Event]:
    started = time.monotonic()
    yield step_event("compose")
    for e in evidence:
        yield Event("evidence", {"key": e.key, "kind": e.kind, "citation": e.citation,
                                 "url": e.url})
    yield Event("plan", {"branches": [{"label": b["label"], "asks": [a["ask"] for a in b["atoms"]]}
                                      for b in answer["branches"]]})
    lines = await compose(question, answer, usage, instruction=instruction)
    for line in lines:
        yield Event("line", {"branch": line.branch, "text": line.text, "keys": list(line.keys)})
    yield step_event("compose", "done", count=len(lines))
    new_answer = {"branches": answer["branches"], "lines": lines_data(lines)}
    res = ReformatResult(new_answer, evidence, usage,
                         {"total_s": round(time.monotonic() - started, 1)})
    yield Event("final", {"answer": new_answer, "text": res.text,
                          "cost_usd": round(usage.cost_usd, 4), "timings": res.timings})
    if result is not None:
        result["result"] = res
