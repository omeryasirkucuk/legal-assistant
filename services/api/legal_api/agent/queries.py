"""Search phrases written by a cheap model: statute-language phrases for a question, and a
decision-search phrase for a sub-question.

Statute phrases:

Lawyers and statutes name the same thing differently ("division in kind" in practice,
"dividing the property" in the code), and the small embedding model does not bridge every
such gap. A cheap call rewrites the question into a few statute-language phrases; their
results are fused with the question's own. Noise is removed later by screening.
"""

from __future__ import annotations

import json

from legal_api import llm
from legal_api.config import get_settings
from legal_api.prompts import prompt

MAX_QUERIES = 3

_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["queries"],
    "additionalProperties": False,
}


async def statute_queries(question: str, usage: llm.Usage) -> list[str]:
    response = await llm.create(
        "cheap", usage, "queries", max_tokens=2000, system=prompt("search_queries"),
        messages=[{"role": "user", "content": question}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return []
    return [q.strip() for q in json.loads(text)["queries"] if q.strip()][:MAX_QUERIES]


_CASE_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


async def case_query(ask: str, usage: llm.Usage) -> str:
    """A short decision-search phrase for a sub-question the planner gave none for."""
    response = await llm.create(
        "cheap", usage, "queries", max_tokens=1500, system=prompt("case_query"),
        messages=[{"role": "user", "content": ask}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _CASE_SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    return json.loads(text)["query"].strip() if text else ""
