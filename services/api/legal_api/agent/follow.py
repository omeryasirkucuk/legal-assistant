"""Follow the cross-references of articles that answer the question.

An article often leaves part of its rule to another one ("the notice and the legal period in
articles 260 and 288 of the Code of Obligations"), so the answer is incomplete without the
referenced article. References are resolved against the statute index:

- to an article of an indexed law named exactly (or of the same law): fetched by its label,
  and kept if the decision model judges it relevant to the question;
- to a law that is not indexed, or only partly matches an indexed name (typically a repealed
  law whose successor kept the name, e.g. the former Code of Obligations and the current
  Turkish Code of Obligations, whose article numbers differ): candidates are found by content, searching with the referring
  sentence, and a language model picks the article that took over the referenced rule. That
  choice needs knowledge the text does not state (old and new numbering), which the decision
  model lacks. It only decides which article is read; the answer is still cited from that
  article's own text.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import asyncpg

from legal_api import decisions, llm
from legal_api.agent.screen import ANSWERS, MAX_TEXT_CHARS
from legal_api.config import get_settings
from legal_api.prompts import prompt
from legal_api.retrieval.references import Reference, find_references, name_match
from legal_api.retrieval.statutes import StatuteHit, get_article, indexed_laws, search_statutes

CONTENT_HITS = 10            # candidates searched per reference resolved by content
MAX_BY_LABEL = 30            # decision-model calls per question for references by label
SUCCESSOR_EXCERPT_CHARS = 1200
SUCCESSOR_VOTES = 3

NEEDED = ("Answer yes if the candidate article states a rule (for example a period, condition "
          "or procedure) that a complete answer to the question needs, because the referring "
          "article relies on it.")

# A verdict per candidate: free selection of a few labels varied from run to run (the same
# input gave three different picks in three runs); judging each candidate in turn does not.
_SUCCESSOR_SCHEMA = {
    "type": "object",
    "properties": {
        "referenced_rule": {"type": "string"},
        "review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"article": {"type": "string"},
                               "sets_referenced_rule": {"type": "boolean"}},
                "required": ["article", "sets_referenced_rule"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["referenced_rule", "review"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Followed:
    hit: StatuteHit
    by: StatuteHit          # the article that makes the reference
    sentence: str           # the referring sentence


@dataclass(frozen=True)
class _Lookup:
    by: StatuteHit
    ref: Reference
    exact_law: str | None             # fetch labels from this law
    content_laws: list[str] | None    # else search by content in these laws (None: all)


def _plan(by: StatuteHit, ref: Reference, laws: dict[str, str]) -> _Lookup:
    if ref.same_law:
        return _Lookup(by, ref, by.law_number, None)
    if ref.law_number:
        if ref.law_number in laws:
            return _Lookup(by, ref, ref.law_number, None)
        return _Lookup(by, ref, None, None)
    matches = {n: name_match(ref.law_name or "", t) for n, t in laws.items()}
    exact = [n for n, m in matches.items() if m == "exact"]
    if exact:
        return _Lookup(by, ref, exact[0], None)
    partial = [n for n, m in matches.items() if m == "partial"]
    return _Lookup(by, ref, None, partial or None)


def _state(question: str, f: Followed) -> dict:
    return {"question": question,
            "referring_article": f"Law {f.by.law_number} ({f.by.law_title}) art. {f.by.label}",
            "referring_sentence": f.sentence,
            "candidate_article": f"Law {f.hit.law_number} ({f.hit.law_title}) art. "
                                 f"{f.hit.label} ({f.hit.heading})",
            "candidate_text": f.hit.text[:MAX_TEXT_CHARS]}


def _merge(lookups: list[_Lookup]) -> list[_Lookup]:
    """One lookup per referring article and target law: an article often names the same
    repealed provision in several sentences, and each sentence alone says only part of what
    it takes from it."""
    merged: dict[tuple, _Lookup] = {}
    for lk in lookups:
        key = (lk.by.id, lk.ref.law_number, lk.ref.law_name,
               tuple(lk.content_laws) if lk.content_laws else None)
        if key not in merged:
            merged[key] = lk
            continue
        old = merged[key]
        sentences = old.ref.sentence if lk.ref.sentence in old.ref.sentence else (
            f"{old.ref.sentence} {lk.ref.sentence}")
        labels = tuple(dict.fromkeys(old.ref.labels + lk.ref.labels))
        merged[key] = _Lookup(old.by, Reference(labels, sentences, old.ref.law_number,
                                                old.ref.law_name), None, old.content_laws)
    return list(merged.values())


async def _by_label(conn: asyncpg.Connection, lookup: _Lookup) -> list[StatuteHit]:
    hits = [await get_article(conn, lookup.exact_law, label) for label in lookup.ref.labels]
    return [h for h in hits if h is not None]


async def _relevant(question: str, followed: list[Followed], usage: llm.Usage
                    ) -> list[Followed]:
    if not followed:
        return []
    async with decisions.client() as client:
        answers = await asyncio.gather(*(
            decisions.yes_probabilities(client, _state(question, f), {"needed": NEEDED}, usage,
                                        "follow") for f in followed))
    return [f for f, p in zip(followed, answers, strict=True)
            if p["needed"] is not None and p["needed"] >= ANSWERS]


async def _successors(lookup: _Lookup, candidates: list[StatuteHit], usage: llm.Usage
                      ) -> list[Followed]:
    """The current articles that took over a provision of a repealed or unindexed law: those
    picked in a majority of independent judgments (single judgments varied between runs)."""
    if not candidates:
        return []
    votes = await asyncio.gather(*(_pick(lookup, candidates, usage)
                                   for _ in range(SUCCESSOR_VOTES)))
    counts: dict[str, int] = {}
    for labels in votes:
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
    by_label = {h.label: h for h in candidates}
    found = [by_label[x] for x, n in counts.items()
             if x in by_label and n * 2 > SUCCESSOR_VOTES]
    found.sort(key=lambda h: -counts[h.label])
    # At most one successor per referenced article.
    return [Followed(h, lookup.by, lookup.ref.sentence)
            for h in found[:len(lookup.ref.labels)]]


async def _pick(lookup: _Lookup, candidates: list[StatuteHit], usage: llm.Usage) -> list[str]:
    listing = "\n".join(
        f"- {h.label} (Law {h.law_number} {h.law_title}; {h.heading}): "
        f"{' '.join(h.text.split())[:SUCCESSOR_EXCERPT_CHARS]}" for h in candidates)
    content = (f"Referring article: Law {lookup.by.law_number} ({lookup.by.law_title}) art. "
               f"{lookup.by.label}\nReferring sentence: {lookup.ref.sentence}\n"
               f"Referenced articles: {', '.join(lookup.ref.labels)}\n\n"
               f"<candidates>\n{listing}\n</candidates>")
    response = await llm.create(
        "cheap", usage, "follow", max_tokens=4000, system=prompt("successor"),
        messages=[{"role": "user", "content": content}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _SUCCESSOR_SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return []
    return list(dict.fromkeys(r["article"].strip() for r in json.loads(text)["review"]
                              if r["sets_referenced_rule"]))


async def follow_references(db: asyncpg.Pool, question: str, answering: list[StatuteHit],
                            usage: llm.Usage) -> list[Followed]:
    """Articles referenced by `answering`: by label when relevant to the question, and the
    current successors of provisions of repealed or unindexed laws."""
    if not answering or not decisions.enabled():
        return []
    known = {h.id for h in answering}
    labelled: dict[int, Followed] = {}
    by_content: list[tuple[_Lookup, list[StatuteHit]]] = []
    pending: list[_Lookup] = []
    async with db.acquire() as conn:
        laws = await indexed_laws(conn)
        for by in answering:
            for ref in find_references(by.text):
                lookup = _plan(by, ref, laws)
                if lookup.exact_law:
                    for hit in await _by_label(conn, lookup):
                        if hit.id not in known:
                            labelled.setdefault(hit.id, Followed(hit, by, ref.sentence))
                else:
                    pending.append(lookup)
        for lookup in _merge(pending):
            by_content.append((lookup, await search_statutes(
                conn, lookup.ref.sentence, limit=CONTENT_HITS, laws=lookup.content_laws)))
    groups = await asyncio.gather(
        _relevant(question, list(labelled.values())[:MAX_BY_LABEL], usage),
        *(_successors(lookup, hits, usage) for lookup, hits in by_content))
    out: dict[int, Followed] = {}
    for group in groups:
        for f in group:
            if f.hit.id not in known:
                out.setdefault(f.hit.id, f)
    return list(out.values())
