"""Petition types: their outline and the statute articles that set what they must contain.

Each type is a file in playbooks/tr/petitions/ with a small header (id, name, articles as
"law/article") and the outline in Turkish; `<type>.practice.md` beside it holds what was
learnt from published samples. The articles are read from the statute index when
a petition is drafted, so the required contents are cited from the law itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from legal_api.config import REPO_ROOT

PETITIONS_DIR = REPO_ROOT / "playbooks" / "tr" / "petitions"


@dataclass(frozen=True)
class PetitionType:
    id: str
    name: str
    articles: tuple[tuple[str, str], ...]   # (law number, article label)
    outline: str
    practice: str = ""      # notes learnt from published samples (drafting/study.py)


def _parse(path: Path) -> PetitionType:
    text = path.read_text(encoding="utf-8")
    _, header, outline = text.split("---", 2)
    fields = {}
    for line in header.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    articles = tuple(tuple(a.split("/", 1)) for a in json.loads(fields["articles"]))
    practice = path.with_suffix(".practice.md")
    return PetitionType(fields["id"], fields["name"], articles, outline.strip(),
                        practice.read_text(encoding="utf-8").strip() if practice.exists() else "")


@cache
def petition_types() -> dict[str, PetitionType]:
    types = [_parse(p) for p in sorted(PETITIONS_DIR.glob("*.md"))
             if not p.name.endswith(".practice.md")]
    return {t.id: t for t in types}
