"""Where a passage the lawyer selected in the editor sits in the draft's text.

The editor shows bold without its ** marks and may join lines differently, so the passage
is matched with ** marks dropped and whitespace runs counted as one space, then mapped back
to offsets in the stored text.
"""

from __future__ import annotations

import re


def _squeezed(text: str) -> tuple[str, list[int]]:
    """The text without ** and with whitespace runs as one space, and for each kept
    character its offset in the original."""
    out, where, i = [], [], 0
    while i < len(text):
        if text.startswith("**", i):
            i += 2
            continue
        if text[i].isspace():
            j = i
            while j < len(text) and text[j].isspace():
                j += 1
            if out and out[-1] != " ":
                out.append(" ")
                where.append(i)
            i = j
            continue
        out.append(text[i])
        where.append(i)
        i += 1
    return "".join(out), where


def locate(text: str, passage: str, within: tuple[int, int] | None = None) -> tuple[int, int] | None:
    """(start, end) of the passage in the text, or None when it is not there exactly once."""
    lo, hi = within or (0, len(text))
    hay, where = _squeezed(text[lo:hi])
    needle = re.sub(r"\s+", " ", passage.replace("**", "")).strip()
    if not needle or hay.count(needle) != 1:
        return None
    at = hay.index(needle)
    return lo + where[at], lo + where[at + len(needle) - 1] + 1
