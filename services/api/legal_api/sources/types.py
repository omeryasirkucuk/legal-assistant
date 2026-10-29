"""Source-neutral records returned by every adapter.

Citation metadata (court, case numbers, dates, article numbers) is always copied from the
source's structured fields; nothing downstream may synthesise it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Court(StrEnum):
    YARGITAY = "yargitay"
    DANISTAY = "danistay"
    ISTINAF = "istinaf"        # regional appeal courts (BAM)
    YEREL = "yerel"            # first-instance courts
    KYB = "kyb"                # appeals in the interest of law
    AYM_BIREYSEL = "aym_bireysel"
    AYM_NORM = "aym_norm"


@dataclass(frozen=True)
class DecisionRef:
    """A decision as listed in search results."""

    source_id: str              # "<court>:<id in source system>"
    court: Court
    chamber: str                # court and chamber name as the source writes it
    case_no: str | None         # case number, "2009/11739"
    decision_no: str | None     # decision number
    decision_date: str | None   # ISO "YYYY-MM-DD"
    url: str                    # official public page


@dataclass(frozen=True)
class Decision:
    ref: DecisionRef
    text: str


@dataclass(frozen=True)
class StatuteRef:
    statute_id: str             # Bedesten legislation id
    number: str                 # law number, "6098"
    title: str
    kind: str                   # Bedesten type name, e.g. "KANUN", "YONETMELIK"
    gazette_no: str | None
    url: str


@dataclass(frozen=True)
class Article:
    statute: StatuteRef
    article_id: str             # Bedesten article id
    number: str | None          # article label: "315", "269/a", "ek 1"
    text: str
    updated_at: str | None
    url: str
