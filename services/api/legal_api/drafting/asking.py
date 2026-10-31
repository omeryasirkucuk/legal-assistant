"""Whether to ask the lawyer for facts before drafting, and what to ask.

Asking every time would tire the lawyer; never asking gave a petition made of placeholders
from a four-line request. So the decision depends on how much is missing and on the lawyer:
- The facts a petition of this kind is built on (drafting/cases.py) are checked against the
  whole conversation by the cheap model: given, partly given, or missing.
- A missing essential fact counts 1 toward asking, a partly given one half; a fact that only
  strengthens the petition counts a quarter of that, so a thin request is told from a full
  one that lacks a detail or two (measured on a four-line divorce request: essentials alone
  scored exactly at the old threshold and the model's run-to-run variance decided; with the
  rest it scores near 2.9, while a detailed request stays near 1). The petition is written
  straight away unless the score reaches the threshold.
- The threshold follows the lawyer's habit: one who usually answers the questions is asked
  sooner, one who usually says "write without them" is asked only when nothing essential is
  known. It is never asked twice in a row, and never when the message says to write directly.
- When the petition is written with facts missing, they go to the writer as the checklist.
Asking costs one cheap call and no research, so a question turn is quick and nearly free.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from legal_api import llm
from legal_api.drafting.cases import CaseKind, case_kinds, general_kind
from legal_api.locale import message
from legal_api.prompts import prompt

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 5
MAX_REQUESTS = 12
GAPS_MAX_TOKENS = 6000   # ten facts with questions and a dozen requests; 2,500 cut it off
HELPFUL = 0.25          # weight of a fact that only strengthens the petition
ASK_AT = 2.0            # score at which the lawyer is asked
EAGER_AT = 1.25         # for a lawyer who usually answers
HABIT_MARGIN = 2        # answers (or skips) ahead of the other that make a habit
WEIGHT = {"missing": 1.0, "partial": 0.5, "given": 0.0}
_SCHEMA = {
    "type": "object",
    "properties": {"requests": {"type": "array", "items": {"type": "string"}},
                   "facts": {"type": "array", "items": {
        "type": "object",
        "properties": {"index": {"type": "integer"},
                       "state": {"type": "string", "enum": list(WEIGHT)},
                       "question": {"type": "string"},
                       "options": {"type": "array", "items": {"type": "string"}}},
        "required": ["index", "state", "question", "options"], "additionalProperties": False}}},
    "required": ["requests", "facts"],
    "additionalProperties": False,
}


@dataclass
class Gaps:
    score: float = 0.0                         # how much is missing (see the module notes)
    questions: list[dict] = field(default_factory=list)   # [{question, options}], essential first
    # What the petition will ask the court for, settled before it is written: left to the
    # writer, the same request got the car's interim measure in one run and not the next.
    requests: list[str] = field(default_factory=list)


def kind_of(case_kind: str | None) -> CaseKind:
    return case_kinds().get(case_kind or "", general_kind())


async def find_gaps(conversation: str, kind: CaseKind, usage: llm.Usage) -> Gaps:
    facts = [*kind.critical, *kind.helpful]
    listing = "\n".join(f"{i}. {f}" for i, f in enumerate(facts))
    response = await llm.create(
        "cheap", usage, "draft_gaps", max_tokens=GAPS_MAX_TOKENS, system=prompt("draft_gaps"),
        messages=[{"role": "user", "content": (
            f"<facts>\n{listing}\n</facts>\n<requests>\n{kind.requests}\n</requests>\n"
            f"<conversation>\n{conversation}\n</conversation>")}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text) if text else {"facts": [], "requests": []}
    except json.JSONDecodeError:
        # An unreadable check must not stop the petition: it is written without asking.
        logger.warning("facts check unreadable (stop reason %s)", response.stop_reason)
        return Gaps()
    found = data["facts"]
    open_ = sorted((f for f in found if 0 <= f["index"] < len(facts) and f["state"] != "given"
                    and f["question"].strip()), key=lambda f: f["index"])
    score = sum(WEIGHT[f["state"]] * (1.0 if f["index"] < len(kind.critical) else HELPFUL)
                for f in open_)
    return Gaps(round(score, 2), [{"question": f["question"].strip(),
                             "options": [o.strip() for o in f["options"] if o.strip()][:4]}
                            for f in open_][:MAX_QUESTIONS],
                [r.strip() for r in data["requests"] if r.strip()][:MAX_REQUESTS])


def threshold(habit: dict, essentials: int) -> float:
    answered, skipped = int(habit.get("answered", 0)), int(habit.get("skipped", 0))
    if skipped - answered >= HABIT_MARGIN:
        return float(essentials)          # only when about nothing essential is known
    if answered - skipped >= HABIT_MARGIN:
        return EAGER_AT
    return ASK_AT


def should_ask(gaps: Gaps, kind: CaseKind, habit: dict, write_now: bool,
               just_asked: bool) -> bool:
    if write_now or just_asked or not gaps.questions:
        return False
    return gaps.score >= threshold(habit, len(kind.critical))


def question_text(gaps: Gaps) -> str:
    lines = [message("drafting", "ask_intro"), ""]
    lines += [f"{n}. {q['question']}" for n, q in enumerate(gaps.questions, 1)]
    return "\n".join([*lines, "", message("drafting", "ask_outro")])


def record(habit: dict, skipped: bool) -> dict:
    """The lawyer's reply to a question turn: answered, or asked to write without."""
    key = "skipped" if skipped else "answered"
    return {**habit, key: int(habit.get(key, 0)) + 1}
