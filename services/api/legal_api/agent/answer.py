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
from legal_api.agent.candidates import screened
from legal_api.agent.candidates import search as search_candidates
from legal_api.agent.compose import Line, compose_branch, lines_data, short_text
from legal_api.agent.decompose import Branch, decompose
from legal_api.agent.follow import follow_references
from legal_api.agent.sources import SourceFinder
from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.grounding.normalize import tr_capitalize
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
    referenced: list[str] = field(default_factory=list)   # "6098/315 <- 2004/269"
    lines: list[Line] = field(default_factory=list)       # the composed short answer
    trace: dict = field(default_factory=dict)              # candidates behind the plan

    def structure(self) -> dict:
        return {"branches": [
            {"label": b.label,
             "atoms": [atom_dict(self.answers[(i, j)]) if (i, j) in self.answers
                       else {"ask": a.ask, "found": False, "segments": []}
                       for j, a in enumerate(b.atoms)]}
            for i, b in enumerate(self.branches)], "lines": lines_data(self.lines)}

    @property
    def short(self) -> str:
        return short_text(self.lines)

    @property
    def text(self) -> str:
        """The stored message: short answer, then every cited sub-answer as the detail."""
        return message_text(self.short, plain_text(self.structure()))

    @property
    def ungrounded(self) -> list[AtomAnswer]:
        return [a for a in self.answers.values() if not a.grounded]


def atom_dict(a: AtomAnswer) -> dict:
    return {"ask": a.atom.ask, "found": a.found and a.grounded,
            "segments": [{"text": s.text, "keys": list(s.keys)} for s in a.segments]
            if a.found and a.grounded else []}


def message_text(short: str, detail: str) -> str:
    return f"<short>\n{short}\n</short>\n<detail>\n{detail}\n</detail>"


def plain_text(structure: dict) -> str:
    lines = []
    for b in structure["branches"]:
        parts = []
        for atom in b["atoms"]:
            if not atom["found"]:
                parts.append(message("status", "not_found", ask=atom["ask"]))
                continue
            text = "".join(s["text"] for s in atom["segments"]).strip()
            keys = dict.fromkeys(key for segment in atom["segments"] for key in segment["keys"])
            markers = "".join(f" [[{key}]]" for key in keys if f"[[{key}]]" not in text)
            parts.append(text + markers)
        lines.append(f"- {tr_capitalize(b['label'])}: {' '.join(parts)}")
    return "\n".join(lines)


def status_event(name: str, /, **values) -> Event:
    return Event("status", {"message": message("status", name, **values)})


def step_event(name: str, state: str = "active", **counts: int) -> Event:
    """Progress the UI shows as a checklist: which step runs, what it has found so far."""
    return Event("step", {"name": name, "state": state, **counts})


async def answer_events(question: str, history: list[dict] | None = None,
                        result: dict | None = None,
                        search_text: str | None = None,
                        usage: llm.Usage | None = None) -> AsyncIterator[Event]:
    """Streams the answer. If `result` is given, it receives the AnswerResult under "result".
    `search_text` replaces the question for finding candidate articles (a follow-up question
    is searched together with the question it follows).

    Events, in order: steps as they start and finish; the plan; then, while sub-questions are
    answered in parallel, every new source, every sub-answer, and the short-answer line of a
    branch as soon as all of its sub-answers are in; finally the whole answer."""
    usage, ledger = usage or llm.Usage(), EvidenceLedger()
    started = time.monotonic()
    timings: dict[str, float] = {}

    def mark(name: str) -> None:
        timings[name] = round(time.monotonic() - started, 1)

    db = await asyncpg.create_pool(asyncpg_dsn(), min_size=2, max_size=8, init=register_vector)
    gateway = Gateway()
    try:
        finder = SourceFinder(ledger, db, gateway)
        lookup = search_text or question
        yield step_event("search")
        hits = await search_candidates(db, lookup, usage)
        yield step_event("search", "done", count=len(hits))
        yield step_event("screen")
        candidates = await screened(db, lookup, hits, usage)
        yield step_event("screen", "done", count=len(candidates.answering))
        yield step_event("references")
        candidates.referenced = await follow_references(db, lookup, candidates.answering,
                                                        usage)
        yield step_event("references", "done", count=len(candidates.referenced))
        yield step_event("plan")
        branches = await decompose(question, history or [], usage, candidates)
        mark("decompose_s")
        total = sum(len(b.atoms) for b in branches)
        yield step_event("plan", "done", branches=len(branches), count=total)
        yield Event("plan", {"branches": [{"label": b.label, "asks": [a.ask for a in b.atoms]}
                                          for b in branches]})
        yield step_event("answer", done=0, count=total)

        res = AnswerResult(question, branches, {}, ledger, usage, timings,
                           candidates.trace()["referenced"], trace=candidates.trace())
        queue: asyncio.Queue = asyncio.Queue()

        async def run_atom(i: int, j: int, atom) -> None:
            await queue.put(("atom", i, j, await answer_atom(atom, finder, usage)))

        async def run_line(i: int) -> None:
            structure = res.structure()
            await queue.put(("line", i, await compose_branch(question, structure, i, usage)))

        tasks = [asyncio.create_task(run_atom(i, j, atom))
                 for i, b in enumerate(branches) for j, atom in enumerate(b.atoms)]
        lines: dict[int, Line] = {}
        announced: set[str] = set()
        waiting_lines = 0
        while len(res.answers) < total or waiting_lines:
            kind, i, *rest = await queue.get()
            if kind == "atom":
                j, done = rest
                res.answers[(i, j)] = done
                for e in ledger:
                    if e.key not in announced:
                        announced.add(e.key)
                        yield Event("evidence", {"key": e.key, "kind": e.kind,
                                                 "citation": e.citation, "url": e.url})
                yield Event("atom", {"branch": i, "index": j, **atom_dict(done)})
                yield step_event("answer", done=len(res.answers), count=total)
                if all((i, k) in res.answers for k in range(len(branches[i].atoms))):
                    tasks.append(asyncio.create_task(run_line(i)))
                    waiting_lines += 1
            else:
                waiting_lines -= 1
                line = rest[0]
                if line is not None:
                    lines[i] = line
                    yield Event("line", {"branch": i, "text": line.text,
                                         "keys": list(line.keys)})
        mark("atoms_s")
        yield step_event("answer", "done", done=total, count=total)
        res.lines = [lines[i] for i in sorted(lines)]
        mark("total_s")
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
