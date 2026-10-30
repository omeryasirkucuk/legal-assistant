"""What a message in an ongoing chat asks for.

- new: a legal question that does not depend on the earlier answer;
- reformat: a change to how the earlier answer is presented (shorter, as a list, simpler);
  answered from the earlier answer's own cited sub-answers, without new retrieval;
- followup: a legal question that builds on the earlier one ("and for bills of exchange?");
  retrieved for together with the question it follows.

The decision model makes this judgment from the text. Without one, a message after an
answer is treated as a follow-up, as before.
"""

from __future__ import annotations

from typing import Literal

from legal_api import decisions, llm

Route = Literal["new", "reformat", "followup"]

INSTRUCTIONS = ("A lawyer is chatting with a legal research assistant. Decide what the new "
                "message asks for, given the previous question and the previous answer.")
CRITERIA = {
    "new": "A new legal question that can be answered without the previous answer.",
    "reformat": "A request to present the previous answer differently (shorter, as a list or "
                "table, simpler words, only some part of it) without asking anything new "
                "about the law.",
    "followup": "A legal question that continues the previous one: asks about a further "
                "case, condition, exception or consequence, or refers to it with words like "
                "'this', 'that case', 'and for ...'.",
}


async def route(message: str, previous_question: str | None, previous_answer: str | None,
                usage: llm.Usage) -> Route:
    if not previous_question or not previous_answer:
        return "new"
    if not decisions.enabled():
        return "followup"
    state = {"previous_question": previous_question,
             "previous_answer": previous_answer[:6000], "new_message": message}
    async with decisions.client() as client:
        picked = await decisions.choose(client, state, INSTRUCTIONS, CRITERIA, usage, "route")
    return picked[0] if picked else "followup"
