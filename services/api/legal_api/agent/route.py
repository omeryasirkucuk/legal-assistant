"""What a message in an ongoing chat asks for.

- new: a legal question that does not depend on the earlier answer;
- reformat: a change to how the earlier answer is presented (shorter, as a list, simpler);
  answered from the earlier answer's own cited sub-answers, without new retrieval;
- followup: a legal question that builds on the earlier one ("and for bills of exchange?");
  retrieved for together with the question it follows.

The decision model makes this judgment from the text. Without one, a message after an
answer is classified by the configured cheap language model.
"""

from __future__ import annotations

import json
import re
from typing import Literal

import anthropic
import httpx

from legal_api import decisions, llm
from legal_api.locale import chat_turns

Route = Literal["new", "reformat", "followup", "greeting", "thanks", "help", "contextual"]

INSTRUCTIONS = ("A lawyer is chatting with a legal research assistant. Decide what the new "
                "message asks for, in the active matter. Resolve references using earlier_user_messages when provided. A request that adds a new deliverable or corrects facts is a followup even if it also asks for a summary.")
CRITERIA = {
    "greeting": "Only greets the assistant. No question, case fact or work request.",
    "thanks": "Only expresses gratitude. No additional request or case fact.",
    "help": "Only asks what the application can do. No specific legal question or task.",
    "new": "A new legal question that can be answered without the previous answer.",
    "reformat": "Only a change to how the previous answer is presented (shorter, as a list or "
                "table, simpler words, only part of it). Nothing is asked that the previous "
                "answer does not already contain.",
    "followup": "Asks something the previous answer did not cover, about the same matter: "
                "what to do next, the steps or stages, the procedure, a further case, "
                "condition, correction, answer to a pending question, exception or document to draft.",
}


def direct_intent(message: str) -> str | None:
    """Only match complete utterances; a greeting introducing a question needs research."""
    phrase = " ".join(re.findall(r"\w+", message.casefold().replace("i\u0307", "i")))
    for intent, entry in chat_turns().items():
        if phrase in entry["phrases"]:
            return intent
    return None


async def route(message: str, previous_question: str | None, previous_answer: str | None,
                usage: llm.Usage, earlier_requests: list[str] | None = None,
                uploaded_names: list[str] | None = None) -> Route:
    if not previous_question or not previous_answer:
        return "new"
    state = {"previous_question": previous_question[:6000],
             "previous_answer": previous_answer[:6000], "new_message": message}
    if uploaded_names:
        state["new_documents"] = uploaded_names
    if earlier_requests:
        state["earlier_user_messages"] = earlier_requests
    if decisions.enabled():
        async with decisions.client() as client:
            picked = await decisions.choose(client, state, INSTRUCTIONS, CRITERIA, usage, "route")
        if picked:
            return picked[0]
    try:
        response = await llm.create("cheap", usage, "route", max_tokens=256,
                                    system=INSTRUCTIONS + " Return only the matching label. "
                                    + json.dumps(CRITERIA),
                                    messages=[{"role": "user", "content": json.dumps(
                                        state, ensure_ascii=False)}])
        label = next((b.text.strip().lower() for b in response.content if b.type == "text"), "")
        if label in CRITERIA:
            return label
    except (anthropic.APIError, httpx.HTTPError):
        pass
    return "contextual"
