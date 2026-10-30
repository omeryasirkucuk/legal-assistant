"""The statute articles shown to the planner, grouped by how sure we are that they matter.

- answering: candidates the decision model confirmed, read in full;
- referenced: articles those refer to (R1, R2, ...), read in full; the planner says for each
  whether the answer needs it and what to ask, and code adds that sub-question (decompose.py);
- to review: uncertain candidates, as excerpts for the planner to judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from legal_api import llm
from legal_api.agent.follow import Followed, follow_references
from legal_api.agent.queries import statute_queries
from legal_api.agent.screen import screen
from legal_api.retrieval.hybrid import fuse
from legal_api.retrieval.statutes import StatuteHit, indexed_laws, search_statutes

CANDIDATE_ARTICLES = 24
CONFIRMED_CHARS = 4000   # answering or referenced: shown (nearly) in full
REVIEW_CHARS = 600       # uncertain: an excerpt for the planner to judge
REFERENCE_SENTENCE_CHARS = 400


@dataclass
class Candidates:
    answering: list[StatuteHit] = field(default_factory=list)
    referenced: list[Followed] = field(default_factory=list)
    to_review: list[StatuteHit] = field(default_factory=list)
    laws: dict[str, str] = field(default_factory=dict)   # indexed law number -> title
    unscreened: int = 0      # candidates the decision model gave no answer for

    def trace(self) -> dict:
        """Counts stored with the answer, to diagnose a weak plan without rerunning it."""
        return {"answering": [f"{h.law_number}/{h.label}" for h in self.answering],
                "referenced": [f"{f.hit.law_number}/{f.hit.label} <- {f.by.law_number}/"
                               f"{f.by.label}" for f in self.referenced],
                "to_review": len(self.to_review), "unscreened": self.unscreened}

    def reference_id(self, index: int) -> str:
        return f"R{index + 1}"

    def text(self) -> str:
        parts = []
        if self.answering:
            parts.append(_group("answers_question",
                                [_line(h, CONFIRMED_CHARS) for h in self.answering]))
        if self.referenced:
            parts.append(_group("referenced_provisions", [
                f"[{self.reference_id(i)}] {_referenced_line(f)}"
                for i, f in enumerate(self.referenced)]))
        if self.to_review:
            parts.append(_group("to_review", [_line(h, REVIEW_CHARS) for h in self.to_review]))
        return "\n".join(parts)


def _group(tag: str, lines: list[str]) -> str:
    return f"<{tag}>\n" + "\n".join(lines) + f"\n</{tag}>"


def _line(h: StatuteHit, chars: int) -> str:
    return (f"- Law {h.law_number} ({h.law_title}) art. {h.label} ({h.heading}): "
            f"{' '.join(h.text.split())[:chars]}")


def _referenced_line(f: Followed) -> str:
    return (f"Law {f.hit.law_number} ({f.hit.law_title}) art. {f.hit.label} "
            f"({f.hit.heading}), referenced by Law {f.by.law_number} art. {f.by.label} in: "
            f"\"{f.sentence[:REFERENCE_SENTENCE_CHARS]}\" Text: "
            f"{' '.join(f.hit.text.split())[:CONFIRMED_CHARS]}")


async def search(db: asyncpg.Pool, question: str, usage: llm.Usage) -> list[StatuteHit]:
    """The question's own results fused (by rank) with those of statute-language phrases."""
    queries = [question, *await statute_queries(question, usage)]
    async with db.acquire() as conn:
        lists = [await search_statutes(conn, q, limit=CANDIDATE_ARTICLES) for q in queries]
    by_id = {h.id: h for hits in lists for h in hits}
    scores = fuse([[h.id for h in hits] for hits in lists])
    ranked = sorted(scores, key=lambda i: -scores[i])
    return [by_id[i] for i in ranked[:CANDIDATE_ARTICLES]]


async def screened(db: asyncpg.Pool, question: str, hits: list[StatuteHit],
                   usage: llm.Usage) -> Candidates:
    """Candidates after screening, before references are followed."""
    async with db.acquire() as conn:
        laws = await indexed_laws(conn)
    result = await screen(question, hits, usage)
    return Candidates(
        answering=[s.hit for s in result if s.answers],
        to_review=[s.hit for s in result if not s.answers and not s.rejected],
        laws=laws, unscreened=sum(s.p_answers is None for s in result))


async def candidate_provisions(db: asyncpg.Pool, question: str, usage: llm.Usage) -> Candidates:
    candidates = await screened(db, question, await search(db, question, usage), usage)
    candidates.referenced = await follow_references(db, question, candidates.answering, usage)
    return candidates
