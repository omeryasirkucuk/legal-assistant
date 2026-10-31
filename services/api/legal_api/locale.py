"""Access to Turkish-language strings kept under the repo-level locales/tr directory."""

from __future__ import annotations

import json
from functools import cache

from legal_api.config import REPO_ROOT

LOCALE_DIR = REPO_ROOT / "locales" / "tr"


@cache
def _bundle(name: str) -> dict[str, str]:
    return json.loads((LOCALE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def institution(key: str) -> str:
    """Official institution name, e.g. institution("yargitay")."""
    return _bundle("institutions")[key]


def with_institution(key: str, chamber: str | None) -> str:
    """Prefix a chamber name with its institution unless the source already did."""
    name = institution(key)
    chamber = (chamber or "").strip()
    if not chamber:
        return name
    if chamber.casefold().startswith(name.casefold()):
        return chamber
    return f"{name} {chamber}"


def citation_template(kind: str) -> str:
    return _bundle("citations")[kind]


def message(bundle: str, key: str, /, **values: object) -> str:
    return _bundle(bundle)[key].format(**values)


def statute_term(key: str) -> str:
    return _bundle("statute_terms")[key]  # type: ignore[return-value]


def reference_terms() -> dict:
    """Words that make up a cross-reference to another article ("... Kanununun 62 nci maddesi")."""
    return _bundle("references")


def law_abbreviations() -> dict[str, str]:
    """Customary abbreviation -> law number (the enforcement law's abbreviation -> "2004")."""
    return _bundle("law_abbreviations")


def number_words() -> dict[str, int]:
    """Number words as they appear in statute text (the word for seven in "seven days") -> their value."""
    return _bundle("numbers")["words"]


def number_units() -> list[str]:
    """Words that, following a number, show it is a quantity (five days)."""
    return _bundle("numbers")["units"]


def section_levels() -> list[str]:
    """Words naming a law's divisions, outermost first (book, part, ...)."""
    return _bundle("statute_terms")["section_levels"]


def style_terms() -> dict:
    """Petition style vocabulary: formal words, opening and closing formulas."""
    return _bundle("style")


def document_labels() -> dict:
    """Weighted words that tell a document's kind and its area of law (files/labels.py)."""
    return _bundle("document_labels")


def calendar_data() -> dict:
    """Holidays, half-day eves and the judicial recess, with their sources (calc/calendar.py)."""
    return _bundle("calendar")


def calculation_terms() -> dict:
    """Wording of a calculation shown to the lawyer and the writer (calc/sources.py)."""
    return _bundle("calculations")


def severance_data() -> dict:
    """Severance pay ceilings, stamp duty and notice periods, with sources (calc/severance.py)."""
    return _bundle("severance")


def matter_terms() -> dict:
    """How a case file is described to the model in its chats (matters/service.py)."""
    return _bundle("matters")


def interest_data() -> dict:
    """Statutory and advance interest rates by period, with sources (calc/interest.py)."""
    return _bundle("interest")


def deadline_rules() -> dict:
    """How the judicial recess and the manner of service bear on a period, by branch."""
    return _bundle("deadline_rules")
