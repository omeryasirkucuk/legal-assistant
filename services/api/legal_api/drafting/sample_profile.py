"""What one of the lawyer's own petitions is: read once by the cheap model when it is added.

A word list sorted petitions by counting words, and a lawyer's divorce petition that told of
violence scored nearly as much for criminal law as for family law (19 against 21); it could
not tell an agreed divorce from a contested one at all, though the two are written very
differently. The model reads the petition instead and says whether it is a petition, its
type, its area of law, the kind of case it is about (drafting/cases.py) and the matter in a
few words. About a tenth of a cent a petition; the result is kept with the sample.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from legal_api import llm
from legal_api.drafting.cases import case_kinds
from legal_api.drafting.types import petition_types
from legal_api.prompts import prompt

READ_CHARS = 8000        # the heading, parties, subject and most of the account
AREAS = ("labour", "tenancy", "family", "enforcement", "criminal", "commercial", "consumer",
         "administrative", "inheritance", "property", "compensation", "other")


@dataclass(frozen=True)
class SampleProfile:
    is_petition: bool = True
    petition_type: str | None = None
    area: str = "other"
    case_kind: str | None = None
    matter: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def of(cls, data: dict | None) -> SampleProfile:
        data = data or {}
        return cls(bool(data.get("is_petition", True)), data.get("petition_type"),
                   data.get("area") or "other", data.get("case_kind"), data.get("matter", ""))


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "is_petition": {"type": "boolean"},
            "petition_type": {"type": "string", "enum": [*petition_types(), "other"]},
            "area": {"type": "string", "enum": list(AREAS)},
            "case_kind": {"type": "string", "enum": [*case_kinds(), "other"]},
            "matter": {"type": "string"},
        },
        "required": ["is_petition", "petition_type", "area", "case_kind", "matter"],
        "additionalProperties": False,
    }


def _system() -> str:
    types = "\n".join(f"{t.id}: {t.name}" for t in petition_types().values())
    kinds = "\n".join(f"{k.id}: {k.name}" for k in case_kinds().values())
    return (f"{prompt('sample_profile')}\n<petition_types>\n{types}\n</petition_types>\n"
            f"<areas>\n{', '.join(AREAS)}\n</areas>\n<case_kinds>\n{kinds}\n</case_kinds>")


async def analyze(title: str, text: str, usage: llm.Usage) -> SampleProfile:
    response = await llm.create(
        "cheap", usage, "sample_profile", max_tokens=1500, system=_system(),
        messages=[{"role": "user", "content": f"<title>{title}</title>\n<document>\n"
                                              f"{text[:READ_CHARS]}\n</document>"}],
        output_config={"format": {"type": "json_schema", "schema": _schema()}})
    data = json.loads(next((b.text for b in response.content if b.type == "text"), "{}"))
    return SampleProfile(
        is_petition=bool(data.get("is_petition", True)),
        petition_type=data.get("petition_type") if data.get("petition_type") in petition_types()
        else None,
        area=data.get("area") if data.get("area") in AREAS else "other",
        case_kind=data.get("case_kind") if data.get("case_kind") in case_kinds() else None,
        matter=(data.get("matter") or "").strip()[:200])
