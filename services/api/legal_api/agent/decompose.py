"""Split a question into branches (the cases the answer depends on) and atomic sub-questions.

Each sub-question is later retrieved for and answered on its own, so (a) retrieval happens at
the granularity of one fact, which is what finds provisions a whole-question search misses,
and (b) an answer can only draw on its own sources, so provisions of different regimes cannot
be blended into one statement. Candidates from the statute index are shown to the model so
coverage comes from the law itself, not only from what the model remembers.

Articles referred to by an answering article were already judged relevant (follow.py). For
each one the planner only writes the sub-question and names its branch (`referenced_review`);
code adds it with both articles as its sources, so a rule stated through a reference cannot be
dropped by how the plan is written.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from legal_api import llm
from legal_api.agent.candidates import Candidates
from legal_api.agent.compose import tag_index
from legal_api.agent.follow import Followed
from legal_api.config import get_settings
from legal_api.grounding.normalize import tr_fold
from legal_api.prompts import prompt
from legal_api.retrieval.statutes import StatuteHit, law_number_of
from legal_api.sources.bedesten_statutes import parse_article_label

MAX_ATOMS = 8
# Thinking plus a review of every candidate; 6,000 was cut off with 20 candidates.
MAX_PLAN_TOKENS = 16000
MAX_REFERENCE_ATOMS = 4
MAX_COVERAGE_ATOMS = 3

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
        "referenced_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "branch": {"type": "string"},
                    "ask": {"type": "string"},
                },
                "required": ["id", "branch", "ask"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["candidate_review", "varies_by", "branches", "referenced_review"],
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


def _label(label: str) -> str | None:
    parsed = parse_article_label(label)
    return parsed[2] if parsed else None


def _cites(branch: Branch, law_number: str, label: str, laws: dict[str, str]) -> bool:
    return any(law_number_of(law, laws) == law_number and _label(art) == _label(label)
               for atom in branch.atoms for law, art in atom.statutes)


def _branch_for(branches: list[Branch], f: Followed, label: str,
                laws: dict[str, str]) -> Branch:
    """The branch a referenced article belongs to: the one the planner named, else the one
    citing the referring article, else a new branch."""
    for b in branches:
        if b.label.casefold() == label.casefold():
            return b
    for b in branches:
        if _cites(b, f.by.law_number, f.by.label, laws):
            return b
    branches.append(Branch(label or f.by.heading))
    return branches[-1]


def _attach_references(branches: list[Branch], review: list[dict], candidates: Candidates
                       ) -> None:
    added = 0
    for entry in review:
        i = tag_index(entry["id"], "R")
        f = candidates.referenced[i] if i is not None and 0 <= i < len(candidates.referenced) \
            else None
        if f is None or not entry["ask"].strip():
            continue
        if added == MAX_REFERENCE_ATOMS:
            break
        branch = _branch_for(branches, f, entry["branch"].strip(), candidates.laws)
        branch.atoms.append(Atom(entry["ask"].strip(),
                                 ((f.hit.law_number, f.hit.label), (f.by.law_number, f.by.label)),
                                 ""))
        added += 1


def _review_of(hit: StatuteHit, review: list[dict]) -> dict | None:
    """The planner's review entry for an article, matched by its label and law number."""
    for entry in review:
        tokens = set(re.findall(r"\d+(?:/\w)?", entry["article"]))
        if hit.label in tokens and (hit.law_number in tokens or len(tokens) == 1):
            return entry
    return None


def _situation(hit: StatuteHit, entry: dict | None) -> str:
    """What the planner said this article regulates, else the article's heading."""
    if entry and entry["situation"].strip():
        return entry["situation"].strip()
    return hit.heading.strip(" :") or f"{hit.law_number}/{hit.label}"


def _cover_answering(branches: list[Branch], question: str, review: list[dict],
                     candidates: Candidates) -> None:
    """Every article screened as answering the question gets a sub-question, unless the
    planner reviewed it and said it does not answer the question. The planner sometimes wrote
    one branch where five regimes apply; this keeps coverage tied to the screened articles
    instead of to how one plan came out, while an explicit rejection still counts."""
    added = 0
    created: dict[str, tuple[Branch, int]] = {}
    for hit in candidates.answering:
        if any(_cites(b, hit.law_number, hit.label, candidates.laws) for b in branches):
            continue
        if added == MAX_COVERAGE_ATOMS:
            break
        entry = _review_of(hit, review)
        if entry is not None and not entry["answers_question"]:
            continue
        situation = _situation(hit, entry)
        branch = next((b for b in branches if tr_fold(b.label) == tr_fold(situation)), None)
        if branch is None:
            branch = Branch(situation)
            branches.append(branch)
        key = tr_fold(situation)
        if key in created:
            # Two articles on the same situation: one sub-question reading both.
            b, j = created[key]
            same = b.atoms[j]
            b.atoms[j] = Atom(same.ask, (*same.statutes, (hit.law_number, hit.label)),
                              same.case_query)
            continue
        branch.atoms.append(Atom(f"{situation}: {question}", ((hit.law_number, hit.label),), ""))
        created[key] = (branch, len(branch.atoms) - 1)
        added += 1


async def decompose(question: str, history: list[dict], usage: llm.Usage,
                    candidates: Candidates) -> list[Branch]:
    content = (f"{question}\n\n<candidate_provisions>\n{candidates.text()}\n"
               f"</candidate_provisions>")
    response = await llm.create(
        "main", usage, "decompose", max_tokens=MAX_PLAN_TOKENS, system=prompt("decompose"),
        messages=[*history, {"role": "user", "content": content}],
        output_config={"effort": get_settings().plan_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    if response.stop_reason == "max_tokens":
        raise RuntimeError("plan cut off at the token limit")
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
    _cover_answering(branches, question, data["candidate_review"], candidates)
    _attach_references(branches, data["referenced_review"], candidates)
    return branches
