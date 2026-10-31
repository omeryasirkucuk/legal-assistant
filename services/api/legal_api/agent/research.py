"""Find the sources an answer is written from.

Candidates come from a statute search on the question and on every issue the understanding
step named (in the statutes' own words), plus the articles it named, read from the local
index. The decision model judges each candidate against the question and its legal
characterisation; the clear ones and the best of the rest are kept, the articles they refer
to are followed, and court decisions are added when the answer depends on practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

from legal_api import llm
from legal_api.agent.follow import follow_references
from legal_api.agent.power import POWERS, Power
from legal_api.agent.screen import ANSWERS, NEEDED, screen
from legal_api.agent.sources import Source, SourceFinder
from legal_api.agent.understand import Understanding
from legal_api.retrieval.hybrid import fuse
from legal_api.retrieval.statutes import (
    StatuteHit,
    get_article,
    neighbours,
    procedure_siblings,
    search_statutes,
)

PER_QUERY = 12
MAX_CANDIDATES = 90    # all results of up to 7 searches of 12
MAX_ARTICLES = 12
RELEVANT = 0.6        # kept when among the best, below the "answers" threshold
ISSUE_MIN = 0.3       # an issue's best result is kept unless judged below this
ISSUE_TOP = 3         # an issue's source is chosen among its own top results first
HINT_MIN = 0.2        # a named article is kept unless judged below this
MAX_SIBLINGS = 6
NEIGHBOUR_OF = 4       # the best kept articles whose neighbours are judged too
NEIGHBOUR_SPAN = 3
MAX_NEIGHBOURS = 3
SEARCH_DECISIONS = 5    # decision passages kept when the lawyer asked for decisions
SEARCH_LIVE = 6         # decisions read from live search then


@dataclass
class Research:
    sources: list[Source] = field(default_factory=list)
    trace: dict = field(default_factory=dict)


def screening_question(question: str, u: Understanding) -> str:
    return f"{question}\n(Legal characterisation: {u.characterisation})" \
        if u.characterisation else question


@dataclass
class Candidates:
    hits: list[StatuteHit]
    hinted: set[int]                 # articles the understanding step named
    per_issue: list[list[int]]       # each issue's best results, best first


async def candidates(db: asyncpg.Pool, question: str, u: Understanding) -> Candidates:
    """Fused search results plus the named articles."""
    queries = [question, *(phrase for _, phrase in u.issues)]
    async with db.acquire() as conn:
        lists = [await search_statutes(conn, q, limit=PER_QUERY) for q in queries]
        hinted = [await get_article(conn, law, art) for law, art in u.statute_hints]
    by_id = {h.id: h for hits in lists for h in hits}
    scores = fuse([[h.id for h in hits] for hits in lists])
    # Every result of every search is judged: cutting the fused list lost the enforcement
    # article whenever only the question's own search ranked it.
    ranked = [by_id[i] for i in sorted(scores, key=lambda i: -scores[i])][:MAX_CANDIDATES]
    ranked_ids = {r.id for r in ranked}
    per_issue = [[h.id for h in hits if h.id in ranked_ids] for hits in lists[1:]]
    hints = {h.id: h for h in hinted if h is not None}
    for h in hints.values():
        if h.id not in ranked_ids:
            ranked.append(h)
    return Candidates(ranked, set(hints), per_issue)


def select(scored: list[tuple[StatuteHit, float | None]], found: Candidates,
           limit: int = MAX_ARTICLES
           ) -> tuple[list[StatuteHit], list[StatuteHit]]:
    """(articles that answer the question, all articles kept), best first.

    In order, up to the limit: articles judged to answer the question; for every issue its
    best-judged result unless clearly irrelevant, so a route or precondition the answer must
    cover is not left without a source (one run lost the enforcement route this way); the
    articles the understanding step named (the offence's own article next to the reduction
    rule); the rest by judgment."""
    p_of = {h.id: (p or 0.0) for h, p in scored}
    by_id = {h.id: h for h, _ in scored}
    answering = sorted((i for i in by_id if p_of[i] >= ANSWERS), key=lambda i: -p_of[i])
    # An issue's guaranteed source: the best-judged among all of its search results.
    # Taken from the issue's own top results first: the best-judged of all its results was
    # often an article another issue already brought (the notice-period article for the
    # severance-pay issue), which left that issue without its own source (law 1475 art. 14,
    # first in its search, judged 0.53).
    issue_best = [_issue_source(top, p_of) for top in found.per_issue]
    issue_best = [i for i in issue_best if i is not None and p_of[i] >= ISSUE_MIN]
    # A named article from memory can carry a wrong law number; one judged clearly
    # unrelated is dropped.
    hinted = [i for i in found.hinted if i in by_id and p_of[i] >= HINT_MIN]
    rest = sorted((i for i in by_id if p_of[i] >= RELEVANT), key=lambda i: -p_of[i])
    ids = list(dict.fromkeys([*answering, *issue_best, *hinted, *rest]))[:limit]
    kept = [by_id[i] for i in ids]
    return [h for h in kept if p_of[h.id] >= ANSWERS], kept


def _issue_source(top: list[int], p_of: dict[int, float]) -> int | None:
    judged = [i for i in top if i in p_of]
    own = [i for i in judged[:ISSUE_TOP] if p_of[i] >= ISSUE_MIN]
    pool = own or judged
    return max(pool, key=lambda i: p_of[i], default=None)


async def siblings(db: asyncpg.Pool, kept: list[StatuteHit]) -> list[StatuteHit]:
    """The lettered continuations of kept articles: a procedure runs over 269, 269/a ..."""
    have = {h.id for h in kept}
    out: list[StatuteHit] = []
    async with db.acquire() as conn:
        for h in kept:
            for s in await procedure_siblings(conn, h):
                if s.id not in have and len(out) < MAX_SIBLINGS:
                    have.add(s.id)
                    out.append(s)
    return out


async def nearby(db: asyncpg.Pool, ask: str, kept: list[StatuteHit], judged: set[int],
                 usage: llm.Usage) -> list[StatuteHit]:
    """Articles next to the best kept ones that are judged relevant too. A code keeps related
    rules side by side, and the one that answers can use other words than the lawyer: the
    partition rule (civil code art. 699, "sharing") was not found by any search for
    "dissolution of co-ownership" while art. 696 three articles before it was."""
    have = {h.id for h in kept} | judged
    near: dict[int, StatuteHit] = {}
    async with db.acquire() as conn:
        for h in kept[:NEIGHBOUR_OF]:
            for n in await neighbours(conn, h.law_number, h.label, NEIGHBOUR_SPAN):
                if n.id not in have:
                    near.setdefault(n.id, n)
    if not near:
        return []
    screened = await screen(ask, list(near.values()), usage, NEEDED)
    good = sorted((s for s in screened if (s.p_answers or 0) >= RELEVANT),
                  key=lambda s: -(s.p_answers or 0))
    return [s.hit for s in good[:MAX_NEIGHBOURS]]


async def research(db: asyncpg.Pool, finder: SourceFinder, question: str, u: Understanding,
                   usage: llm.Usage, progress, power: Power = POWERS["balanced"]) -> Research:
    """`progress(step, state, **counts)` reports each step for the UI."""
    progress("search", "active")
    found = await candidates(db, question, u)
    hits = found.hits
    progress("search", "done", count=len(hits))
    progress("screen", "active")
    screened = await screen(screening_question(question, u), hits, usage, NEEDED)
    answering, kept = select([(s.hit, s.p_answers) for s in screened], found,
                             power.max_articles)
    kept += await nearby(db, screening_question(question, u), kept, {h.id for h in hits}, usage)
    kept += await siblings(db, kept)
    progress("screen", "done", count=len(kept))
    progress("references", "active")
    # Judged against the question with its characterisation: a follow-up ("is there a
    # precedent on this?") does not state the case by itself.
    ask = screening_question(question, u)
    followed = await follow_references(db, ask, answering, usage)
    progress("references", "done", count=len(followed))
    sources = [finder.article_source(h) for h in kept]
    sources += [finder.article_source(
        f.hit, (finder.article_source(f.by).evidence.citation, f.sentence.strip())) for f in followed]
    decisions: list[Source] = []
    # Decisions are searched whenever practice matters, and always when the lawyer asks for
    # decisions themselves (a request for precedents once got none: nothing was searched).
    asked_for_cases = u.task == "search"
    fast_petition = u.task == "drafting" and power.name == "fast"   # no decisions (D50)
    if not fast_petition and (u.case_law_query or u.task == "consultation" or asked_for_cases
                              or power.always_decisions):
        progress("caselaw", "active")
        decisions = await finder.decisions_for(
            u.case_law_query or u.characterisation, ask, usage,
            keep=max(SEARCH_DECISIONS if asked_for_cases else 0, power.keep_decisions),
            live_limit=max(SEARCH_LIVE if asked_for_cases else 0, power.live_decisions),
            precedents=asked_for_cases)
        progress("caselaw", "done", count=len(decisions))
    unique: dict[str, Source] = {}
    for s in [*sources, *decisions]:
        unique.setdefault(s.evidence.key, s)
    return Research(list(unique.values()), {
        "candidates": len(hits), "answering": [f"{h.law_number}/{h.label}" for h in answering],
        "kept": [f"{h.law_number}/{h.label}" for h in kept],
        "referenced": [f"{f.hit.law_number}/{f.hit.label}" for f in followed],
        "decisions": len(decisions)})
