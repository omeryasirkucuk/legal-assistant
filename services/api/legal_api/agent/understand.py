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
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import httpx

from legal_api import llm
from legal_api.calc.deadlines import UNITS
from legal_api.config import get_settings
from legal_api.drafting.cases import case_kinds
from legal_api.drafting.export import FORMATS
from legal_api.drafting.sample_profile import AREAS
from legal_api.drafting.types import petition_types
from legal_api.prompts import prompt

TASKS = ("lookup", "consultation", "drafting", "search", "review", "workspace", "clarification")
SHAPES = ("single", "amount", "answers", "routes", "plan", "draft", "list")
MAX_ISSUES = 8
MAX_HINTS = 10
MAX_DEADLINES = 4
MAX_PENALTIES = 6
PETITION_TYPES = (*petition_types(), "other")
CASE_KINDS = (*case_kinds(), "other")

# Keep classification labels as strings to limit the compiled grammar size. The prompt
# lists the accepted labels and understand() validates them before use.
_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "enum": list(TASKS)},
        "requested_precedents": {"type": "boolean"},
        "research_request": {"type": "string"},
        "blocking_question": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "shape": {"type": "string"},
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
        "petition_type": {"type": "string"},
        "output_format": {"type": "string"},
        "case_kind": {"type": "string"},
        "area": {"type": "string"},
        "write_now": {"type": "boolean"},
        "calendar": {"type": "boolean"},
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
                           "extras_monthly": {"type": "number"},
                           "service_months": {"type": "integer"},
                           "estimate_current_period": {"type": "boolean"}},
            "required": ["start_date", "end_date", "gross_monthly", "extras_monthly",
                         "service_months", "estimate_current_period"],
            "additionalProperties": False}},
        "deadlines": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "start_date": {"type": "string"},
                           "amount": {"type": "integer"},
                           "unit": {"type": "string", "enum": list(UNITS)},
                           "law": {"type": "string"}, "article": {"type": "string"}},
            "required": ["label", "start_date", "amount", "unit", "law", "article"],
            "additionalProperties": False}},
        "court_costs": {"type": "array", "items": {
            "type": "object",
            "properties": {"value": {"type": "number"},
                           "court": {"type": "string", "enum": ["sulh", "asliye"]},
                           "measure": {"type": "string",
                                       "enum": ["proportional", "fixed", "unknown"]},
                           "bodily_harm": {"type": "boolean"},
                           "filed_on": {"type": "string"}},
            "required": ["value", "court", "measure", "bodily_harm", "filed_on"],
            "additionalProperties": False}},
        "penalties": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "law": {"type": "string"},
                           "article": {"type": "string"}, "paragraph": {"type": "string"},
                           "modifiers": {"type": "array", "items": {
                               "type": "object",
                               "properties": {"law": {"type": "string"},
                                              "article": {"type": "string"},
                                              "paragraph": {"type": "string"},
                                              "item": {"type": "string"}},
                               "required": ["law", "article", "paragraph", "item"],
                               "additionalProperties": False}}},
            "required": ["label", "law", "article", "paragraph", "modifiers"],
            "additionalProperties": False}},
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "clarify": {"type": "array", "items": {
            "type": "object",
            "properties": {"question": {"type": "string"},
                           "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["question", "options"], "additionalProperties": False}},
    },
    "required": ["task", "requested_precedents", "research_request", "blocking_question", "questions", "shape", "characterisation", "issues", "statute_hints",
                 "case_law_query", "petition_type", "output_format", "case_kind", "area",
                 "write_now", "calendar", "deadlines", "penalties", "court_costs", "severance", "interest", "missing_facts",
                 "clarify"],
    "additionalProperties": False,
}


@dataclass
class Understanding:
    task: str = "lookup"
    requested_precedents: bool = False
    research_request: str = ""
    blocking_question: str = ""
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
    calendar: bool = False              # about the deadlines the lawyer recorded (matters/agenda.py)
    gap_trace: dict = field(default_factory=dict)   # how the ask-or-write decision was made
    requests: list[str] = field(default_factory=list)   # a petition's requests, settled first
    deadlines: list[dict] = field(default_factory=list)  # periods to compute (calc/sources.py)
    severance: dict | None = None                        # dates and pay for severance pay
    interest: list[dict] = field(default_factory=list)   # principal and span for interest
    penalties: list[dict] = field(default_factory=list)  # offences whose range is computed
    court_costs: dict | None = None     # value, court and filing date for fees and appeal limits

    def trace(self) -> dict:
        return {"task": self.task, "shape": self.shape, "characterisation": self.characterisation,
                "issues": [n for n, _ in self.issues],
                "hints": [f"{law}/{art}" for law, art in self.statute_hints], **self.gap_trace}


def _system() -> str:
    kinds = "\n".join(f"{k.id}: {k.name}" for k in case_kinds().values())
    return f"{prompt('understand')}\n<case_kinds>\n{kinds}\n</case_kinds>"


# Providers can reject a valid schema while compiling its grammar. Remember that rejection
# for the configured model so later requests need only one model call.
_grammar_rejected: set[tuple[bool, str | None, str]] = set()


def _grammar_error(exc: anthropic.BadRequestError | httpx.HTTPStatusError) -> bool:
    if exc.response.status_code != 400:
        return False
    try:
        error = exc.response.json().get("error", {})
        metadata = error.get("metadata") or {}
        raw = metadata.get("raw") or ""
        message = f"{error.get('message', '')} {raw}".lower()
    except (ValueError, AttributeError):
        return False
    return "compiled grammar is too large" in message or "schema is too complex for compilation" in message


def _valid_response(value, schema: dict) -> bool:
    expected = schema["type"]
    if expected == "object":
        props = schema["properties"]
        return (isinstance(value, dict) and value.keys() == props.keys()
                and all(_valid_response(value[key], shape) for key, shape in props.items()))
    if expected == "array":
        return isinstance(value, list) and all(_valid_response(item, schema["items"]) for item in value)
    types = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}
    return type(value) in types[expected] and ("enum" not in schema or value in schema["enum"])


async def _completion(content: str, history: list[dict], usage: llm.Usage, system: str,
                      max_tokens: int):
    config = {"effort": get_settings().answer_effort}
    request = {"max_tokens": max_tokens,
               "messages": [*history, {"role": "user", "content": content}]}
    route = (llm.openai_for("cheap"), llm.routed("cheap"), llm.model_for("cheap"))
    if route not in _grammar_rejected:
        try:
            return await llm.create(
                "cheap", usage, "understand", system=system, **request,
                output_config={**config, "format": {"type": "json_schema", "schema": _SCHEMA}})
        except (anthropic.BadRequestError, httpx.HTTPStatusError) as exc:
            if not _grammar_error(exc):
                raise
            _grammar_rejected.add(route)
    schema = json.dumps(_SCHEMA, ensure_ascii=False, separators=(",", ":"))
    system += f"\nYalnızca bu şemaya uygun bir JSON nesnesi döndür. Markdown veya açıklama yazma.\n{schema}"
    response = await llm.create("cheap", usage, "understand", system=system, **request,
                                output_config=config)
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text.removeprefix("```json\n").removesuffix("```").strip()
    if not _valid_response(json.loads(text), _SCHEMA):
        raise ValueError("Invalid analysis response structure")
    return llm.Completion([llm.TextBlock("text", text)], response.model, response.usage)


async def understand(message: str, history: list[dict], usage: llm.Usage,
                     laws: dict[str, str] | None = None) -> Understanding:
    """`laws`: the indexed laws (number -> title), so named articles carry the right law
    number (one run named the enforcement article with the civil procedure law's number)."""
    # The date, so "served today" or "last Monday" become dates for the period calculator.
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    content = f"<today>{today.isoformat()}</today>\n\n{message}"
    if laws:
        listing = "\n".join(f"{n}: {t}" for n, t in sorted(laws.items()))
        content = f"<indexed_laws>\n{listing}\n</indexed_laws>\n\n{content}"
    response = await _completion(content, history, usage, _system(),
                                 2600 if len(message) <= 1000 else 4500)
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return Understanding()
    data = json.loads(text)
    return Understanding(
        task=data["task"] if data["task"] in TASKS else "lookup",
        requested_precedents=data.get("requested_precedents") is True,
        research_request=data.get("research_request", "").strip()[:2000],
        blocking_question=data.get("blocking_question", "").strip()[:500],
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
        calendar=bool(data.get("calendar")),
        deadlines=[d for d in data.get("deadlines", []) if d.get("start_date")][:MAX_DEADLINES],
        court_costs=next(iter(data.get("court_costs") or []), None),
        penalties=[p for p in data.get("penalties", []) if p.get("law") and p.get("article")]
        [:MAX_PENALTIES],
        interest=[i for i in data.get("interest", []) if i.get("principal") and i.get("start_date")][:3],
        severance=next(iter(data.get("severance") or []), None),
        clarify=[{"question": c["question"].strip(),
                  "options": [o.strip() for o in c["options"] if o.strip()][:4]}
                 for c in data["clarify"] if c["question"].strip() and c["options"]][:3])
