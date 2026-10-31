"""Before anything is searched: what the lawyer wants, and what the case is in law.

One cheap call returns the kind of task (a single fact, a case consultation, a draft, a
search, a review), the legal characterisation of the facts, the issues the answer rests on
with a statute-language search phrase each, articles the model knows to be relevant, a
case-law query when practice matters, and facts that are missing. Retrieval then searches
for every issue, not only for the question's words (a tenant who does not pay is "tenant
default", which leads to the right article even if the lawyer never wrote that phrase).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from legal_api import llm
from legal_api.calc.deadlines import UNITS
from legal_api.config import get_settings
from legal_api.drafting.cases import case_kinds
from legal_api.drafting.export import FORMATS
from legal_api.drafting.sample_profile import AREAS
from legal_api.drafting.types import petition_types
from legal_api.prompts import prompt

TASKS = ("lookup", "consultation", "drafting", "search", "review")
SHAPES = ("single", "answers", "routes", "plan", "draft", "list")
MAX_ISSUES = 8
MAX_HINTS = 10
MAX_DEADLINES = 4
PETITION_TYPES = (*petition_types(), "other")
CASE_KINDS = (*case_kinds(), "other")

_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "enum": list(TASKS)},
        "questions": {"type": "array", "items": {"type": "string"}},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "characterisation": {"type": "string"},
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "search_phrase": {"type": "string"}},
            "required": ["name", "search_phrase"], "additionalProperties": False}},
        "statute_hints": {"type": "array", "items": {
            "type": "object",
            "properties": {"law": {"type": "string"}, "article": {"type": "string"}},
            "required": ["law", "article"], "additionalProperties": False}},
        "case_law_query": {"type": "string"},
        "petition_type": {"type": "string", "enum": list(PETITION_TYPES)},
        "output_format": {"type": "string", "enum": [*FORMATS, "none"]},
        "case_kind": {"type": "string", "enum": list(CASE_KINDS)},
        "area": {"type": "string", "enum": list(AREAS)},
        "write_now": {"type": "boolean"},
        "interest": {"type": "array", "items": {
            "type": "object",
            "properties": {"principal": {"type": "number"}, "start_date": {"type": "string"},
                           "end_date": {"type": "string"},
                           "kind": {"type": "string", "enum": ["statutory", "advance", "unknown"]}},
            "required": ["principal", "start_date", "end_date", "kind"],
            "additionalProperties": False}},
        "severance": {"type": "array", "items": {
            "type": "object",
            "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"},
                           "gross_monthly": {"type": "number"},
                           "extras_monthly": {"type": "number"}},
            "required": ["start_date", "end_date", "gross_monthly", "extras_monthly"],
            "additionalProperties": False}},
        "deadlines": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "start_date": {"type": "string"},
                           "amount": {"type": "integer"},
                           "unit": {"type": "string", "enum": list(UNITS)},
                           "law": {"type": "string"}, "article": {"type": "string"}},
            "required": ["label", "start_date", "amount", "unit", "law", "article"],
            "additionalProperties": False}},
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "clarify": {"type": "array", "items": {
            "type": "object",
            "properties": {"question": {"type": "string"},
                           "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["question", "options"], "additionalProperties": False}},
    },
    "required": ["task", "questions", "shape", "characterisation", "issues", "statute_hints",
                 "case_law_query", "petition_type", "output_format", "case_kind", "area",
                 "write_now", "deadlines", "severance", "interest", "missing_facts",
                 "clarify"],
    "additionalProperties": False,
}


@dataclass
class Understanding:
    task: str = "lookup"
    characterisation: str = ""
    issues: list[tuple[str, str]] = field(default_factory=list)      # (name, search phrase)
    statute_hints: list[tuple[str, str]] = field(default_factory=list)  # (law, article)
    case_law_query: str = ""
    missing_facts: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)   # the lawyer's own questions, in order
    shape: str = "single"                                 # the form the answer should take
    clarify: list[dict] = field(default_factory=list)     # [{question, options}] to ask back
    petition_type: str = "other"                          # for drafting: drafting.types id
    output_format: str | None = None                      # file format the message names
    case_kind: str = "other"                              # for drafting: drafting.cases id
    area: str = "other"                                   # area of law (sample_profile.AREAS)
    write_now: bool = False             # the lawyer asked for the petition without questions
    gap_trace: dict = field(default_factory=dict)   # how the ask-or-write decision was made
    requests: list[str] = field(default_factory=list)   # a petition's requests, settled first
    deadlines: list[dict] = field(default_factory=list)  # periods to compute (calc/sources.py)
    severance: dict | None = None                        # dates and pay for severance pay
    interest: list[dict] = field(default_factory=list)   # principal and span for interest

    def trace(self) -> dict:
        return {"task": self.task, "shape": self.shape, "characterisation": self.characterisation,
                "issues": [n for n, _ in self.issues],
                "hints": [f"{law}/{art}" for law, art in self.statute_hints], **self.gap_trace}


def _system() -> str:
    kinds = "\n".join(f"{k.id}: {k.name}" for k in case_kinds().values())
    return f"{prompt('understand')}\n<case_kinds>\n{kinds}\n</case_kinds>"


async def understand(message: str, history: list[dict], usage: llm.Usage,
                     laws: dict[str, str] | None = None) -> Understanding:
    """`laws`: the indexed laws (number -> title), so named articles carry the right law
    number (one run named the enforcement article with the civil procedure law's number)."""
    # The date, so "served today" or "last Monday" become dates for the period calculator.
    content = f"<today>{date.today().isoformat()}</today>\n\n{message}"
    if laws:
        listing = "\n".join(f"{n}: {t}" for n, t in sorted(laws.items()))
        content = f"<indexed_laws>\n{listing}\n</indexed_laws>\n\n{content}"
    response = await llm.create(
        "cheap", usage, "understand", max_tokens=4000, system=_system(),
        messages=[*history, {"role": "user", "content": content}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return Understanding()
    data = json.loads(text)
    return Understanding(
        task=data["task"] if data["task"] in TASKS else "lookup",
        characterisation=data["characterisation"].strip(),
        issues=[(i["name"].strip(), i["search_phrase"].strip())
                for i in data["issues"] if i["search_phrase"].strip()][:MAX_ISSUES],
        statute_hints=[(h["law"].strip(), h["article"].strip())
                       for h in data["statute_hints"]][:MAX_HINTS],
        case_law_query=data["case_law_query"].strip(),
        missing_facts=[f.strip() for f in data["missing_facts"] if f.strip()][:4],
        questions=[q.strip() for q in data["questions"] if q.strip()][:5],
        shape=data["shape"] if data["shape"] in SHAPES else "single",
        petition_type=data.get("petition_type") if data.get("petition_type") in PETITION_TYPES
        else "other",
        output_format=data.get("output_format") if data.get("output_format") in FORMATS
        else None,
        case_kind=data.get("case_kind") if data.get("case_kind") in CASE_KINDS else "other",
        area=data.get("area") if data.get("area") in AREAS else "other",
        write_now=bool(data.get("write_now")),
        deadlines=[d for d in data.get("deadlines", []) if d.get("start_date")][:MAX_DEADLINES],
        interest=[i for i in data.get("interest", []) if i.get("principal") and i.get("start_date")][:3],
        severance=next((s for s in data.get("severance", [])
                        if s.get("start_date") and s.get("end_date") and s.get("gross_monthly")),
                       None),
        clarify=[{"question": c["question"].strip(),
                  "options": [o.strip() for o in c["options"] if o.strip()][:4]}
                 for c in data["clarify"] if c["question"].strip() and c["options"]][:3])
