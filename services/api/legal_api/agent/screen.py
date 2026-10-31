"""Screen candidate statute articles: does each one, read in full, answer the question?

Each candidate is judged on its own by the decision model, so the set of articles the answer
is built from no longer depends on what the planner notices in a short snippet. Articles the
model confirms are shown to the planner in full; uncertain ones are left for the planner to
judge; clear rejections are dropped. Without a decision model configured, every candidate is
left uncertain and the planner judges them all, as before.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from legal_api import decisions, llm
from legal_api.retrieval.statutes import StatuteHit

# At or above: the article answers the question. Articles that do scored 0.92-0.96 in our
# probes; neighbouring provisions (the consequence of not objecting) 0.79-0.83.
ANSWERS = 0.85
REJECTED = 0.4     # below: dropped
MAX_TEXT_CHARS = 12_000

INSTRUCTIONS = ("You are a Turkish lawyer screening statute articles for a legal question. "
                "Answer yes only if the article text itself states a rule that answers the "
                "question or a case of it (for example the period, condition or procedure "
                "asked about). Topical similarity without such a rule is no.")


@dataclass(frozen=True)
class Screened:
    hit: StatuteHit
    p_answers: float | None     # None: not screened

    @property
    def answers(self) -> bool:
        return self.p_answers is not None and self.p_answers >= ANSWERS

    @property
    def rejected(self) -> bool:
        return self.p_answers is not None and self.p_answers < REJECTED


def state_of(question: str, hit: StatuteHit) -> dict:
    return {"question": question,
            "article": f"Law {hit.law_number} ({hit.law_title}) art. {hit.label} ({hit.heading})",
            "section": hit.section,
            "article_text": hit.text[:MAX_TEXT_CHARS]}


# For writing a whole answer: is the article needed, not only does it answer the question.
NEEDED = ("A lawyer asked the question; its legal characterisation is given. Answer yes if the "
          "article states a rule that a complete answer needs: the rule asked about, a route "
          "or remedy that is available, a mandatory prior step or precondition, a time limit, "
          "or the competent court or authority. Topical similarity without such a rule is no.")


async def screen(question: str, hits: list[StatuteHit], usage: llm.Usage,
                 instructions: str = INSTRUCTIONS) -> list[Screened]:
    if not decisions.enabled():
        return [Screened(h, None) for h in hits]
    async with decisions.client() as client:
        answers = await asyncio.gather(*(
            decisions.yes_probabilities(client, state_of(question, h), {"answers": instructions},
                                        usage, "screen") for h in hits))
    return [Screened(h, a["answers"]) for h, a in zip(hits, answers, strict=True)]
