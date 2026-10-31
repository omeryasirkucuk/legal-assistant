"""Sync core laws into the local statute index (one row per article) and embed them.

    uv run python -m legal_api.corpus.statutes [--laws 2004 6098 ...]

Each law is fetched as one consolidated document (a single request), split at its article
headings, and replaced atomically, so a nightly run keeps the index current. Lettered
articles ("269/a"), additional ("ek") and temporary ("gecici") articles are kept as their own
rows, which is what lets search surface them.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from pgvector.asyncpg import register_vector

from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.embeddings import embed_passages
from legal_api.grounding.normalize import tr_lower
from legal_api.locale import section_levels, statute_term
from legal_api.sources import bedesten_statutes as bs
from legal_api.sources.gateway import Gateway
from legal_api.sources.text import html_to_text

# Core codes a litigator needs daily; extend freely.
CORE_LAWS = ["2004", "6098", "4721", "6100", "5237", "5271", "2577", "6102", "4857", "7036",
             "6325", "634", "1136", "7201", "492", "6502", "2709",
             # The 1971 labour law: its art. 14 (severance pay) is still in force.
             "1475"]


@dataclass(frozen=True)
class ParsedArticle:
    kind: str
    label: str
    heading: str
    text: str
    section: str = ""


def _section_pattern() -> re.Pattern:
    """A division heading ("DÖRDÜNCÜ BÖLÜM", the ordinal sometimes on its own line after
    conversion) and its title: the lines that follow, up to the next blank line."""
    levels = "|".join(re.escape(w) for w in section_levels())
    upper = "A-ZÇĞİÖŞÜÂÎÛ"
    return re.compile(rf"(?m)^[ \t]*(?:[{upper}]+\s+){{1,2}}?(?P<level>{levels})[ \t]*\n"
                      rf"\s*(?P<title>(?:[^\n]*\S[^\n]*\n){{1,3}}?)[ \t]*\n")


def sections_at(document_text: str) -> list[tuple[int, str]]:
    """(position, section path) after every division heading, the path built from the
    innermost heading of each level seen so far (a new chapter resets deeper levels)."""
    levels = section_levels()
    current: dict[int, str] = {}
    out: list[tuple[int, str]] = []
    for m in _section_pattern().finditer(document_text):
        depth = levels.index(m.group("level"))
        current = {d: t for d, t in current.items() if d < depth}
        current[depth] = " ".join(m.group("title").split())
        out.append((m.end(), " > ".join(current[d] for d in sorted(current))))
    return out


def _heading_pattern() -> re.Pattern:
    article = statute_term("article")
    extra = "|".join(re.escape(statute_term(k)) for k in ("additional", "temporary"))
    return re.compile(
        rf"(?im)^[ \t]*(?:(?P<kind>{extra})\s+)?{article}\s*"
        rf"(?P<label>\d+(?:\s*/\s*[^\W\d_])?)\s*[-–—]")


def _clean(segment: str) -> str:
    text = re.sub(r"\s+", " ", segment).strip()
    return re.sub(r" (\(\d+\)) ", r"\n\1 ", text)


def _marginal_title(before: str) -> str:
    """The article's marginal title: the short lines directly above its heading, which may
    wrap over a few lines. Stops at the previous article's sentence end."""
    lines: list[str] = []
    for line in reversed([ln.strip() for ln in before.rstrip().split("\n")]):
        if not line:
            if lines:
                continue
            continue
        if len(line) > 150 or line.endswith((".", ")", ";")) or len(lines) == 3:
            break
        lines.insert(0, line)
    return " ".join(lines)


def split_articles(document_text: str) -> list[ParsedArticle]:
    """Split a consolidated law into articles. Later duplicates (articles of amending laws
    appended after the code itself) are dropped: the first occurrence is the code's own."""
    # The service's text uses CRLF line endings; patterns below work on lines. Zero-width
    # characters inside words are dropped (they reached answers as "\u200b").
    document_text = document_text.replace("\r\n", "\n").replace("\r", "\n")
    document_text = re.sub("[\u200b\u200c\u200d\ufeff]", "", document_text)
    heads = list(_heading_pattern().finditer(document_text))
    sections = sections_at(document_text)
    kinds = {tr_lower(statute_term("additional")): "additional",
             tr_lower(statute_term("temporary")): "temporary"}
    out: list[ParsedArticle] = []
    seen: set[tuple[str, str]] = set()
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(document_text)
        kind = kinds.get(tr_lower(head.group("kind") or ""), "main")
        label = re.sub(r"\s+", "", tr_lower(head.group("label")))
        if kind != "main":
            label = f"{statute_term(kind)} {label}"
        if (kind, label) in seen:
            continue
        seen.add((kind, label))
        heading = _marginal_title(document_text[max(0, head.start() - 400):head.start()])
        body = _clean(document_text[head.start():end])
        # The next article's marginal title sits just above its heading; drop it from this one.
        nxt = heads[i + 1] if i + 1 < len(heads) else None
        if nxt:
            tail = _marginal_title(document_text[max(0, nxt.start() - 400):nxt.start()])
            if tail:
                body = body.removesuffix(_clean(tail)).rstrip()
        section = next((path for pos, path in reversed(sections) if pos <= head.start()), "")
        out.append(ParsedArticle(kind, label, heading, body, section))
    return out


async def fetch_law(statutes: bs.BedestenStatutes, number: str):
    _, refs = await statutes.search(number=number, size=5)
    refs = [r for r in refs if r.kind == "KANUN"] or refs
    if not refs:
        raise LookupError(f"law {number} not found")
    ref = refs[0]
    data = await statutes._post("getDocumentContent",
                                {"documentType": "MEVZUAT", "id": ref.statute_id})
    html = base64.b64decode(data["content"]).decode("utf-8", "replace")
    return ref, split_articles(html_to_text(html))


async def sync(numbers: list[str]) -> None:
    conn = await asyncpg.connect(asyncpg_dsn())
    await register_vector(conn)
    gateway = Gateway()
    statutes = bs.BedestenStatutes(gateway)
    try:
        for number in numbers:
            ref, articles = await fetch_law(statutes, number)
            vectors = embed_passages([f"{a.section}\n{a.heading}\n{a.text}"[:2000]
                                      for a in articles])
            now = datetime.now(UTC)
            async with conn.transaction():
                await conn.execute("DELETE FROM statute_articles WHERE law_number = $1", number)
                await conn.copy_records_to_table(
                    "statute_articles",
                    columns=["law_number", "law_title", "statute_id", "kind", "label",
                             "position", "heading", "section", "text", "url", "fetched_at",
                             "embedding"],
                    records=[(number, ref.title, ref.statute_id, a.kind, a.label, i, a.heading,
                              a.section, a.text, ref.url, now, v)
                             for i, (a, v) in enumerate(zip(articles, vectors, strict=True))])
            print(f"{number} {ref.title}: {len(articles)} articles", flush=True)
    finally:
        await gateway.aclose()
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--laws", nargs="*", default=CORE_LAWS)
    asyncio.run(sync(parser.parse_args().laws))


if __name__ == "__main__":
    main()
