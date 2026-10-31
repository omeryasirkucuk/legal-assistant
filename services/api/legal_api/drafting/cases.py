"""Kinds of case a petition can be about (contested divorce, labour receivables, eviction):
the facts such a petition is built on, the requests it usually makes and how it is written.

Petition types (drafting/types.py) set the procedural form every suit petition shares; a case
kind adds what only that kind of suit needs, which a single outline for all suits could not
give (a divorce petition was drafted with a mediation section and no interim measures). Each
kind is a file in playbooks/tr/petitions/cases/ with a small header (id, name, the petition
types it applies to, a default length in words) and three sections: the facts, a fact marked
with "!" being one the petition cannot be built without; the requests; how it is written.
`_genel.md` holds the facts every petition rests on, used for a case of no listed kind.
Statute articles are not named there: they come from the sources as for every answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from legal_api.drafting.types import PETITIONS_DIR

CASES_DIR = PETITIONS_DIR / "cases"
_SECTION = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class CaseKind:
    id: str
    name: str
    petition_types: tuple[str, ...]
    words: int
    critical: tuple[str, ...]     # facts the petition cannot be built without
    helpful: tuple[str, ...]      # facts that make it stronger
    requests: str
    writing: str

    def guide(self) -> str:
        """What the writer is told about this kind of case."""
        facts = "\n".join([*(f"- {f}" for f in self.critical), *(f"- {f}" for f in self.helpful)])
        return (f"<case_kind>{self.name}</case_kind>\n<case_facts>\n{facts}\n</case_facts>\n"
                f"<case_requests>\n{self.requests}\n</case_requests>\n"
                f"<case_writing>\n{self.writing}\n</case_writing>")


def _parse(path: Path) -> CaseKind:
    _, header, body = path.read_text(encoding="utf-8").split("---", 2)
    fields = dict(line.split(":", 1) for line in header.strip().splitlines())
    fields = {k.strip(): v.strip() for k, v in fields.items()}
    parts = _SECTION.split(body)
    sections = [s.strip() for s in parts[2::2]]     # facts, requests, writing (in this order)
    facts, requests, writing = sections[:3]
    lines = [ln.strip() for ln in facts.splitlines()]
    return CaseKind(fields["id"], fields["name"], tuple(json.loads(fields["petition_types"])),
                    int(fields["words"]),
                    tuple(ln[1:].strip() for ln in lines if ln.startswith("!")),
                    tuple(ln[1:].strip() for ln in lines if ln.startswith("-")),
                    requests, writing)


@cache
def case_kinds() -> dict[str, CaseKind]:
    kinds = [_parse(p) for p in sorted(CASES_DIR.glob("*.md")) if not p.name.startswith("_")]
    return {k.id: k for k in kinds}


@cache
def general_kind() -> CaseKind:
    """The facts every petition rests on, for a case of no listed kind."""
    return _parse(CASES_DIR / "_genel.md")
