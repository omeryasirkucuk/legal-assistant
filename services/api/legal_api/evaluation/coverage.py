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

# One verdict per point with the answer's own words for it: a bare list of booleans marked
# points stated in so many words as missing (an answer citing art. 14 of law 1475 for
# severance pay was graded as not covering it).
_SCHEMA = {
    "type": "object",
    "properties": {"points": {"type": "array", "items": {
        "type": "object",
        "properties": {"point": {"type": "integer"}, "answer_quote": {"type": "string"},
                       "covered": {"type": "boolean"}},
        "required": ["point", "answer_quote", "covered"],
        "additionalProperties": False}}},
    "required": ["points"],
    "additionalProperties": False,
}


async def grade_coverage(question: str, answer: str, points: list[str],
                         usage: llm.Usage) -> list[bool]:
    if not points:
        return []
    # A reply with the wrong number of verdicts (once an empty list) used to be padded with
    # False, scoring a good answer 0/5; it is asked once more, then reported as an error.
    for _ in range(2):
        covered = await _grade(question, answer, points, usage)
        if len(covered) == len(points):
            return covered
    raise RuntimeError(f"coverage grader returned {len(covered)} verdicts for {len(points)}")


async def _grade(question: str, answer: str, points: list[str], usage: llm.Usage
                 ) -> list[bool]:
    numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    response = await llm.create(
        "judge", usage, "eval_coverage", max_tokens=3000, system=_SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{"role": "user", "content": (
            f"<question>\n{question}\n</question>\n<expected_points>\n{numbered}\n"
            f"</expected_points>\n<answer>\n{answer}\n</answer>\n"
            f"For every expected point, in order: its number, the sentence of the answer that "
            f"states it (empty if none), and whether it is covered.")}])
    points_out = json.loads(next(b.text for b in response.content if b.type == "text"))["points"]
    return [p["covered"] and bool(p["answer_quote"].strip()) for p in points_out]
