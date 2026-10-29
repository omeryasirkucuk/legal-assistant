"""Split decision texts into paragraph-aligned chunks that keep their character offsets.

Offsets let the grounding layer map a retrieved chunk back to the exact span of the
original decision text, which is what quotes are verified against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TARGET_CHARS = 1200
MAX_CHARS = 2000

# A paragraph runs from a non-space to the last non-space before a blank line or the end;
# trailing spaces on the line must not hide the boundary.
_PARAGRAPH = re.compile(r"\S(?:.*?\S)?(?=[ \t]*(?:\n[ \t]*\n|\s*\Z))", re.DOTALL)
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    start: int
    text: str


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _PARAGRAPH.finditer(text)]


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Break an over-long paragraph at sentence ends, falling back to a hard cut."""
    spans: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > MAX_CHARS:
        window = text[cursor:cursor + MAX_CHARS]
        cuts = [m.start() for m in _SENTENCE_END.finditer(window) if m.start() >= TARGET_CHARS // 2]
        cut = cursor + (cuts[-1] if cuts else MAX_CHARS)
        spans.append((cursor, cut))
        cursor = cut
        while cursor < end and text[cursor].isspace():
            cursor += 1
    if cursor < end:
        spans.append((cursor, end))
    return spans


def chunk_text(text: str) -> list[Chunk]:
    pieces: list[tuple[int, int]] = []
    for start, end in _paragraph_spans(text):
        pieces.extend(_split_long(text, start, end) if end - start > MAX_CHARS else [(start, end)])

    chunks: list[Chunk] = []
    group_start: int | None = None
    group_end = 0
    for start, end in pieces:
        if group_start is not None and end - group_start > TARGET_CHARS:
            chunks.append(Chunk(len(chunks), group_start, text[group_start:group_end]))
            group_start = None
        if group_start is None:
            group_start = start
        group_end = end
    if group_start is not None:
        chunks.append(Chunk(len(chunks), group_start, text[group_start:group_end]))
    return chunks
