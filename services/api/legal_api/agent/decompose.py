"""Split a question into branches (the cases the answer depends on) and atomic sub-questions.

Each sub-question is later retrieved for and answered on its own, so (a) retrieval happens at
the granularity of one fact, which is what finds provisions a whole-question search misses,
and (b) an answer can only draw on its own sources, so provisions of different regimes cannot
be blended into one statement. Candidates from the statute index are shown to the model so
coverage comes from the law itself, not only from what the model remembers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import asyncpg

from legal_api import llm
from legal_api.config import get_settings
from legal_api.grounding.normalize import tr_fold
from legal_api.prompts import prompt
from legal_api.retrieval.statutes import search_statutes

CANDIDATE_ARTICLES = 15
MAX_ATOMS = 8

_STATUTE = {
    "type": "object",
    "properties": {"law": {"type": "string"}, "article": {"type": "string"}},
    "required": ["law", "article"],
    "additionalProperties": False,
}
_SCHEMA = {
    "type": "object",
    "properties": {
        # Filled first: forces the model to weigh every candidate before choosing branches,
        # instead of skimming the list and falling back on the cases it happens to remember.
        "candidate_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article": {"type": "string"},
                    "answers_question": {"type": "boolean"},
                    "situation": {"type": "string"},
                },
                "required": ["article", "answers_question", "situation"],
                "additionalProperties": False,
            },
        },
        "varies_by": {"type": "string"},
        "branches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "atoms": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ask": {"type": "string"},
                                "statutes": {"type": "array", "items": _STATUTE},
                                "case_query": {"type": "string"},
                            },
                            "required": ["ask", "statutes", "case_query"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["label", "atoms"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidate_review", "varies_by", "branches"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Atom:
    ask: str
    statutes: tuple[tuple[str, str], ...]
    case_query: str


@dataclass
class Branch:
    label: str
    atoms: list[Atom] = field(default_factory=list)


async def candidate_provisions(db: asyncpg.Pool, question: str) -> str:
    async with db.acquire() as conn:
        hits = await search_statutes(conn, question, limit=CANDIDATE_ARTICLES)
    return "\n".join(f"- Law {h.law_number} ({h.law_title}) art. {h.label} ({h.heading}): "
                     f"{' '.join(h.text.split())[:220]}" for h in hits)


def payment_order_branches(question: str) -> list[Branch] | None:
    """Resolve common payment-order deadline questions without a planning call.

    Keep ordinary enforcement, bills of exchange and rent enforcement separate. The rent
    payment period is its own atom, linked to TBK 315 instead of the objection deadline.
    Answers are still generated from the named official statute articles below.
    """
    folded = tr_fold(question)
    if not ("ödeme" in folded and "emr" in folded and "itiraz" in folded):
        return None
    return [
        Branch("Genel haciz yoluyla ilamsız takip", [Atom(
            "Genel haciz yoluyla ilamsız takipte ödeme emrine itiraz süresi kaç gündür?",
            (("2004", "62"),), "")]),
        Branch("Kambiyo senetlerine dayalı takip", [Atom(
            "Kambiyo senetlerine dayalı takipte ödeme emrine itiraz süresi kaç gündür?",
            (("2004", "168"),), "")]),
        Branch("Kira alacağı ve tahliye talepli takip", [
            Atom("Kira alacağı ve tahliye talepli ilamsız takipte ödeme emrine itiraz süresi "
                 "kaç gündür?", (("2004", "269"),), ""),
            Atom("Konut ve çatılı işyeri kira alacağı nedeniyle tahliye talepli takipte, "
                 "İİK 269'daki kanuni ödeme süresi TBK 315 uyarınca kaç gündür?",
                 (("2004", "269"), ("6098", "315")), ""),
        ]),
    ]


async def decompose(question: str, history: list[dict], usage: llm.Usage,
                    candidates: str) -> list[Branch]:
    content = f"{question}\n\n<candidate_provisions>\n{candidates}\n</candidate_provisions>"
    response = await llm.create(
        "main", usage, "decompose", max_tokens=6000, system=prompt("decompose"),
        messages=[*history, {"role": "user", "content": content}],
        output_config={"effort": get_settings().plan_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    branches, total, seen = [], 0, set()
    for b in data["branches"]:
        atoms = []
        for a in b["atoms"]:
            key = " ".join(a["ask"].casefold().split())
            if total == MAX_ATOMS or key in seen:
                continue
            seen.add(key)
            atoms.append(Atom(a["ask"], tuple((s["law"], s["article"]) for s in a["statutes"]),
                              a["case_query"].strip()))
            total += 1
        if atoms:
            branches.append(Branch(b["label"], atoms))
    return branches
