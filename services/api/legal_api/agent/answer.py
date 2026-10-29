"""Grounded question answering: decompose -> per-sub-question retrieval and cited answers ->
compose the short answer. The detail section is generated only when the lawyer opens it
(detail.py), so the short answer is not held back by it.

`answer_events` streams the process as events (type: data):
  status:   {"message"}                         what the assistant is doing right now
  plan:     {"branches": [{label, asks}]}       the cases and sub-questions being answered
  evidence: {"key","kind","citation","url"}     a source an answer may cite
  atom:     {"branch","index","ask","found","segments"}   one sub-question's cited answer
  final:    {"answer","text","cost_usd","timings"}        the composed answer
Grounding is enforced by the citations API (each cited passage is guaranteed to exist in its
source); an answer with no citation is reported as not found rather than shown.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import asyncpg
from pgvector.asyncpg import register_vector

from legal_api import llm
from legal_api.agent.atoms import AtomAnswer, answer_atom
from legal_api.agent.decompose import Branch, candidate_provisions, decompose
from legal_api.agent.sources import SourceFinder
from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import message
from legal_api.sources.gateway import Gateway


@dataclass(frozen=True)
class Event:
    type: str
    data: dict = field(default_factory=dict)


@dataclass
class AnswerResult:
    question: str
    branches: list[Branch]
    answers: dict[tuple[int, int], AtomAnswer]
    ledger: EvidenceLedger
    usage: llm.Usage
    timings: dict[str, float] = field(default_factory=dict)

    def structure(self) -> dict:
        return {"branches": [
            {"label": b.label,
             "atoms": [atom_dict(self.answers[(i, j)]) for j in range(len(b.atoms))]}
            for i, b in enumerate(self.branches)]}

    @property
    def text(self) -> str:
        """Plain-text short answer, for history, search and evaluation."""
        return plain_text(self.structure())

    @property
    def ungrounded(self) -> list[AtomAnswer]:
        return [a for a in self.answers.values() if not a.grounded]


def atom_dict(a: AtomAnswer) -> dict:
    return {"ask": a.atom.ask, "found": a.found and a.grounded,
            "segments": [{"text": s.text, "keys": list(s.keys)} for s in a.segments]
            if a.found and a.grounded else []}


def plain_text(structure: dict) -> str:
    lines = []
    for b in structure["branches"]:
        parts = ["".join(s["text"] for s in a["segments"]).strip() if a["found"]
                 else message("status", "not_found", ask=a["ask"]) for a in b["atoms"]]
        lines.append(f"- {b['label']}: {' '.join(parts)}")
    return "\n".join(lines)


def _status(name: str, /, **values) -> Event:
    return Event("status", {"message": message("status", name, **values)})


async def answer_events(question: str, history: list[dict] | None = None,
                        result: dict | None = None) -> AsyncIterator[Event]:
    """Streams the answer. If `result` is given, it receives the AnswerResult under "result"."""
    usage, ledger = llm.Usage(), EvidenceLedger()
    started = time.monotonic()
    timings: dict[str, float] = {}

    def mark(name: str) -> None:
        timings[name] = round(time.monotonic() - started, 1)

    db = await asyncpg.create_pool(asyncpg_dsn(), min_size=2, max_size=8, init=register_vector)
    gateway = Gateway()
    try:
        finder = SourceFinder(ledger, db, gateway)
        yield _status("planning")
        candidates = await candidate_provisions(db, question)
        branches = await decompose(question, history or [], usage, candidates)
        mark("decompose_s")
        yield Event("plan", {"branches": [{"label": b.label, "asks": [a.ask for a in b.atoms]}
                                          for b in branches]})
        yield _status("answering", count=sum(len(b.atoms) for b in branches))

        async def run(i: int, j: int, atom) -> tuple[int, int, AtomAnswer]:
            return i, j, await answer_atom(atom, finder, usage)

        answers: dict[tuple[int, int], AtomAnswer] = {}
        announced: set[str] = set()
        tasks = [run(i, j, atom) for i, b in enumerate(branches) for j, atom in enumerate(b.atoms)]
        for next_done in asyncio.as_completed(tasks):
            i, j, done = await next_done
            answers[(i, j)] = done
            for e in ledger:
                if e.key not in announced:
                    announced.add(e.key)
                    yield Event("evidence", {"key": e.key, "kind": e.kind,
                                             "citation": e.citation, "url": e.url})
            yield Event("atom", {"branch": i, "index": j, **atom_dict(done)})
        mark("total_s")

        res = AnswerResult(question, branches, answers, ledger, usage, timings)
        yield Event("final", {"answer": res.structure(), "text": res.text,
                              "cost_usd": round(usage.cost_usd, 4), "timings": timings})
        if result is not None:
            result["result"] = res
    finally:
        await gateway.aclose()
        await db.close()


async def answer(question: str, history: list[dict] | None = None) -> AnswerResult:
    holder: dict = {}
    async for _ in answer_events(question, history, holder):
        pass
    return holder["result"]
