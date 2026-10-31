"""How much work an answer gets, chosen by the lawyer as a plain choice, not a model name.

fast: the cheaper model writes, fewer sources, decisions only when needed;
balanced: the default;
deep (Derin araştırma): more sources, decisions always searched with more read, and the
writer thinks longer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Power:
    name: str
    write_role: str          # llm role of the writer
    write_effort: str
    max_articles: int
    always_decisions: bool
    live_decisions: int
    keep_decisions: int


POWERS = {
    "fast": Power("fast", "main", "low", 8, False, 2, 1),
    "balanced": Power("balanced", "write", "low", 12, False, 4, 2),
    "deep": Power("deep", "write", "medium", 16, True, 8, 4),
}
DEFAULT = "balanced"


def power_of(name: str | None) -> Power:
    return POWERS.get(name or DEFAULT, POWERS[DEFAULT])
