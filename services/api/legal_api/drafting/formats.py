"""Which file format a petition is delivered in.

The format named in the message wins and is remembered; otherwise the format the lawyer has
asked for most often; Word when they never asked or when formats are tied.
"""

from __future__ import annotations

from legal_api.drafting.export import FORMATS

DEFAULT = "docx"


def choose(requested: str | None, counts: dict[str, int]) -> str:
    if requested in FORMATS:
        return requested
    asked = {f: n for f, n in counts.items() if f in FORMATS and n > 0}
    if not asked:
        return DEFAULT
    top = max(asked.values())
    leaders = [f for f, n in asked.items() if n == top]
    return leaders[0] if len(leaders) == 1 else DEFAULT


def counted(counts: dict[str, int], requested: str | None) -> dict[str, int]:
    """The counts after a message that named `requested` (unchanged if it named none)."""
    if requested not in FORMATS:
        return dict(counts)
    return {**counts, requested: counts.get(requested, 0) + 1}
