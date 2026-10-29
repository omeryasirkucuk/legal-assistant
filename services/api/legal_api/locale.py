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
    return _bundle("statute_terms")[key]
