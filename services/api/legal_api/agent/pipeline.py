"""Answer a message: understand it, research its sources, write the answer.

Replaces the decompose -> sub-answers -> gists pipeline (agent/answer.py, kept for
comparison), which could only assemble one-sentence facts side by side: it failed on case
consultations and wrote answers no expert would (see docs/STATUS.md known issues 10-11).

Events (type: data): step {name, state, counts}; evidence {key, kind, citation, url};
delta {text} while the answer is written; final {text, checked, cost_usd, timings}.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace

import anthropic
import asyncpg
import httpx
from pgvector.asyncpg import register_vector

from legal_api import llm
from legal_api.agent.answer import Event, step_event
from legal_api.agent.atoms import Segment
from legal_api.agent.power import POWERS, Power
from legal_api.agent.research import Research, research
from legal_api.agent.sources import Source, SourceFinder
from legal_api.agent.understand import Understanding, understand
from legal_api.agent.write import MAX_TOKENS, Written, write
from legal_api.calc.court_costs_sources import court_cost_sources
from legal_api.calc.penalty_sources import penalty_sources
from legal_api.calc.sources import deadline_sources, interest_sources, severance_sources
from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.drafting.asking import find_gaps, kind_of, question_text, should_ask
from legal_api.drafting.brief import StyleBook
from legal_api.drafting.prepare import DRAFT_MAX_TOKENS, drafting_instruction
from legal_api.drafting.style import around_petition
from legal_api.drafting.tidy import tidy
from legal_api.files.context import Attachment, for_understanding, for_writer
from legal_api.grounding.evidence import Evidence, EvidenceLedger
from legal_api.locale import calculation_terms
from legal_api.matters.agenda import Agenda
from legal_api.retrieval.statutes import indexed_laws
from legal_api.sources.gateway import Gateway
from legal_api.workspace.public import PublicResearch
from legal_api.workspace.session import Context, Workspace


@dataclass
class WrittenResult:
    """What chat/service.save_answer stores."""
    question: str
    understanding: Understanding
    written: Written
    ledger: EvidenceLedger | list[Evidence]
    usage: llm.Usage
    timings: dict[str, float] = field(default_factory=dict)
    trace: dict = field(default_factory=dict)
    asked: bool = False      # the turn asked for facts instead of drafting
    workspace: dict | None = None
    workspace_files: list[bytes] = field(default_factory=list)

    @property
    def text(self) -> str:
        """What the chat shows: for a petition, the note and checklist beside the file."""
        if self.understanding.task == "drafting" and not self.asked:
            return around_petition(self.written.text)
        return self.written.text

    @property
    def full_text(self) -> str:
        return self.written.text

    @property
    def short(self) -> str:
        return self.written.text

    @property
    def checked(self) -> dict | None:
        if self.understanding.task == "workspace":
            return None
        return {"issues": [], "claims": self.written.flagged, "citation_check": "source_passages"}

    def structure(self) -> dict:
        return {"format": "written", "task": self.understanding.task,
                "shape": self.understanding.shape, "clarify": self.understanding.clarify,
                **({"asked": True} if self.asked else {}),
                "segments": [{"text": s.text, "keys": list(s.keys)}
                             for s in self.written.segments]}


async def answer_events(question: str, history: list[dict] | None = None,
                        result: dict | None = None, search_text: str | None = None,
                        usage: llm.Usage | None = None, style: StyleBook | None = None,
                        power: Power = POWERS["balanced"],
                        attachments: list[Attachment] | None = None,
                        just_asked: bool = False,
                        agenda: Agenda | None = None,
                        workspace: Context | None = None) -> AsyncIterator[Event]:
    """`style`: the lawyer's style, used when the message asks for a petition; `power`: how
    much work the answer gets; `attachments`: the lawyer's documents for this message;
    `just_asked`: the previous turn asked the lawyer for facts (drafting/asking.py);
    `agenda`: the deadlines the lawyer recorded, a source when the message is about them."""
    attachments = attachments or []
    usage, ledger = usage or llm.Usage(), EvidenceLedger()
    started = time.monotonic()
    timings: dict[str, float] = {}
    queue: asyncio.Queue[Event] = asyncio.Queue()

    def mark(name: str) -> None:
        timings[name] = round(time.monotonic() - started, 1)

    def progress(name: str, state: str, **counts: int) -> None:
        queue.put_nowait(step_event(name, state, **counts))

    db = await asyncpg.create_pool(asyncpg_dsn(), min_size=2, max_size=8, init=register_vector)
    gateway = Gateway()
    try:
        finder = SourceFinder(ledger, db, gateway)
        yield step_event("analyse")
        async with db.acquire() as conn:
            laws = await indexed_laws(conn)
        u = await understand(for_understanding(search_text or question, attachments),
                             history or [], usage, laws)
        mark("understand_s")
        if u.task == "workspace":
            yield step_event("analyse", "done", issues=len(u.issues))
            yield step_event("calculate")
            agent = Workspace(workspace or Context(), finder, PublicResearch(gateway), ledger, usage)
            outcome = await agent.run(question, history or [])
            mark("total_s")
            yield step_event("calculate", "done")
            for source in outcome.sources:
                yield Event("evidence", {"key": source.key, "kind": source.kind,
                                         "citation": source.citation, "url": source.url})
            used = {source.key for source in outcome.sources}
            res = WrittenResult(question, u, Written([Segment(outcome.text)], outcome.text, []),
                                [e for e in ledger if e.key in used], usage, timings, u.trace(),
                                workspace=outcome.snapshot, workspace_files=outcome.files)
            yield Event("final", {"text": res.text, "cost_usd": round(usage.cost_usd, 4),
                                  "timings": timings})
            if result is not None:
                result["result"] = res
            return
        if u.task == "drafting":
            kind = kind_of(u.case_kind)
            gaps = await find_gaps(_conversation(history or [], for_understanding(
                question, attachments)), kind, usage)
            asked = should_ask(gaps, kind, (style or StyleBook()).asking, u.write_now, just_asked)
            u.gap_trace = {"gap_score": gaps.score, "write_now": u.write_now,
                           "just_asked": just_asked, "asked": asked}
            if asked:
                yield step_event("analyse", "done", issues=len(u.issues))
                async for event in _ask(question, u, gaps, usage, ledger, timings, result):
                    yield event
                return
            # Written now: what is still missing goes to the checklist, not to questions under
            # the petition (they repeated the checklist and asked for facts already given).
            u.missing_facts = [q["question"] for q in gaps.questions]
            u.clarify = []
            u.requests = gaps.requests
        yield step_event("analyse", "done", issues=len(u.issues))
        if _calendar_only(u, agenda):
            # "What is due this week?" is answered from the calendar; nothing to search.
            found = Research(trace={"calendar_only": True})
        else:
            task = asyncio.create_task(
                research(db, finder, search_text or question, u, usage, progress, power))
            while not task.done() or not queue.empty():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield getter.result()
                else:
                    getter.cancel()
            found = task.result()
        if u.calendar and agenda is not None:
            found.sources.insert(0, agenda.source(ledger))
            found.trace["calendar"] = True
        instruction, max_tokens = None, MAX_TOKENS
        if u.task == "drafting":
            yield step_event("caselaw")
            instruction = await drafting_instruction(db, finder, found, search_text or question,
                                                     u, style or StyleBook(), usage, power)
            yield step_event("caselaw", "done", count=found.trace.get("ground_precedents", 0))
            max_tokens = DRAFT_MAX_TOKENS
            # Petitions are written by the petition writer unless the lawyer chose the deepest
            # work (D48); without one configured, by the answer writer.
            if power.name != "deep" and llm.routed("draft"):
                power = replace(power, write_role="draft")
                found.trace["writer"] = llm.routed("draft")
        if u.deadlines or u.severance or u.interest or u.penalties or u.court_costs:
            # Periods and amounts are computed in code and given as sources (calc/).
            yield step_event("calculate")
            computed: list[dict] = []
            calculated = await deadline_sources(u.deadlines, finder, ledger, computed)
            found.trace["deadlines_computed"] = computed
            if u.severance:
                calculated += await severance_sources(u.severance, finder, ledger)
            for spec in u.interest:
                calculated += await interest_sources(spec, ledger)
            calculated += await penalty_sources(u.penalties, finder, ledger)
            if u.court_costs:
                calculated += await court_cost_sources(u.court_costs, finder, ledger)
            # Keep the full calculation and its direct sources if research found them too.
            by_key: dict[str, Source] = {}
            for source in [*calculated, *found.sources]:
                by_key.setdefault(source.evidence.key, source)
            found.sources = list(by_key.values())
            count = len({s.evidence.key for s in calculated if s.evidence.kind == "calculation"})
            found.trace["calculations"] = count
            yield step_event("calculate", "done", count=count)
        mark("research_s")
        for e in ledger:
            yield Event("evidence", {"key": e.key, "kind": e.kind, "citation": e.citation,
                                     "url": e.url})
        written: Written | None = None
        yield step_event("write")
        try:
            async for item in write(search_text or question, u, found.sources, usage, instruction,
                                    max_tokens=max_tokens, power=power,
                                    context=for_writer(attachments)):
                if isinstance(item, str):
                    # A petition is delivered as a file, not streamed into the chat.
                    if u.task != "drafting":
                        yield Event("delta", {"text": item})
                else:
                    written = item
        except (anthropic.APIStatusError, httpx.HTTPStatusError) as exc:
            if u.task == "drafting" or not llm.unavailable(exc):
                raise
            written = _available_calculations(found.sources)
            if written is None:
                raise
            found.trace["calculation_fallback"] = True
        if written is None:
            raise RuntimeError("No verified answer was produced.")
        if u.task == "drafting" and written is not None:
            written = Written(written.segments, tidy(written.text), written.flagged)
        mark("total_s")
        yield step_event("write", "done")
        res = WrittenResult(question, u, written, ledger, usage, timings,
                            {**u.trace(), **found.trace})
        yield Event("final", {"text": res.text, "checked": res.checked,
                              "clarify": u.clarify,
                              "cost_usd": round(usage.cost_usd, 4), "timings": timings})
        if result is not None:
            result["result"] = res
    finally:
        await gateway.aclose()
        await db.close()


def _available_calculations(sources: list[Source]) -> Written | None:
    calculations = [s.evidence for s in sources if s.evidence.kind == "calculation"]
    if not calculations:
        return None
    segments = [Segment("\n\n".join(e.text.splitlines()), (e.key,)) for e in calculations]
    intro = calculation_terms()["fallback_intro"]
    body = "\n\n".join(f"{segment.text} [[{segment.keys[0]}]]" for segment in segments)
    return Written(segments, f"{intro}\n\n{body}", [])


def _calendar_only(u: Understanding, agenda: Agenda | None) -> bool:
    return (agenda is not None and u.calendar and u.task == "lookup" and not u.issues
            and not u.statute_hints and not u.deadlines and not u.case_law_query)


def _conversation(history: list[dict], message: str) -> str:
    turns = [f"{'Lawyer' if t['role'] == 'user' else 'Assistant'}: {t['content']}" for t in history]
    return "\n\n".join([*turns, f"Lawyer: {message}"])


async def _ask(question: str, u: Understanding, gaps, usage: llm.Usage, ledger: EvidenceLedger,
               timings: dict, result: dict | None) -> AsyncIterator[Event]:
    """A question turn: the facts the petition needs, with one-click answers where possible."""
    text = question_text(gaps)
    u.clarify = [q for q in gaps.questions if q["options"]]
    res = WrittenResult(question, u, Written([Segment(text)], text, []), ledger, usage,
                        timings, {**u.trace(), "asked": len(gaps.questions)}, asked=True)
    yield Event("delta", {"text": text})
    yield Event("final", {"text": text, "checked": res.checked, "clarify": u.clarify,
                          "asked": True, "cost_usd": round(usage.cost_usd, 4),
                          "timings": timings})
    if result is not None:
        result["result"] = res


async def rewrite_events(instruction: str, question: str, previous_text: str,
                         sources: list[Source], usage: llm.Usage,
                         result: dict | None = None) -> AsyncIterator[Event]:
    """A reformat request: the previous answer written again from the same sources."""
    started = time.monotonic()
    ledger = EvidenceLedger()
    for s in sources:
        yield Event("evidence", {"key": s.evidence.key, "kind": s.evidence.kind,
                                 "citation": s.evidence.citation, "url": s.evidence.url})
    yield step_event("compose")
    u = Understanding(task="lookup")
    written: Written | None = None
    async for item in write(question, u, sources, usage, instruction=instruction,
                            previous=previous_text):
        if isinstance(item, str):
            yield Event("delta", {"text": item})
        else:
            written = item
    yield step_event("compose", "done", count=1)
    res = WrittenResult(question, u, written, ledger, usage,
                        {"total_s": round(time.monotonic() - started, 1)}, {"route": "reformat"})
    res.ledger = [s.evidence for s in sources]   # the earlier answer's sources, kept as they were
    yield Event("final", {"text": res.text, "checked": res.checked,
                          "cost_usd": round(usage.cost_usd, 4), "timings": res.timings})
    if result is not None:
        result["result"] = res


async def answer(question: str, history: list[dict] | None = None) -> WrittenResult:
    holder: dict = {}
    async for _ in answer_events(question, history, holder):
        pass
    return holder["result"]
