"""Grades whether an answer covers the points a lawyer expects (eval/golden must_cover).

Independent of the in-product reviewer: it sees only the question, the expected points and
the rendered answer, so a weakness shared by the answer model and the reviewer still shows.
"""

from __future__ import annotations

import json

from legal_api import llm

_SYSTEM = (
    "You grade a Turkish legal assistant's answer. For each expected point, decide whether "
    "the answer states it, in substance (wording may differ). A point counts only if the "
    "answer actually states it, not if it merely hints at it. Reply in the requested JSON.")

_SCHEMA = {
    "type": "object",
    "properties": {"covered": {"type": "array", "items": {"type": "boolean"}}},
    "required": ["covered"],
    "additionalProperties": False,
}


async def grade_coverage(question: str, answer: str, points: list[str],
                         usage: llm.Usage) -> list[bool]:
    if not points:
        return []
    numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    response = await llm.create(
        "judge", usage, "eval_coverage", max_tokens=1000, system=_SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{"role": "user", "content": (
            f"<question>\n{question}\n</question>\n<expected_points>\n{numbered}\n"
            f"</expected_points>\n<answer>\n{answer}\n</answer>\n"
            f"Return one boolean per expected point, in order.")}])
    covered = json.loads(next(b.text for b in response.content if b.type == "text"))["covered"]
    return (covered + [False] * len(points))[:len(points)]
