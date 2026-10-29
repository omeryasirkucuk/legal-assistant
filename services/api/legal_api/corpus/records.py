"""Map rows of the public decision dataset to corpus records with official source links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from legal_api.locale import institution, with_institution

ICTIHAT_PAGE = "https://mevzuat.adalet.gov.tr/ictihat"
DANISTAY_PAGE = "https://karararama.danistay.gov.tr/getDokuman"
AYM_BANK = "https://kararlarbilgibankasi.anayasa.gov.tr"


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    source: str
    chamber: str
    case_no: str | None
    decision_no: str | None
    decision_date: date | None
    url: str
    text: str
    raw_sha256: str


def _url(source: str, doc_id: str, case_no: str | None, decision_no: str | None) -> str:
    if source in ("yargitay", "emsal"):
        return f"{ICTIHAT_PAGE}/{doc_id}"
    if source == "danistay":
        return f"{DANISTAY_PAGE}?id={doc_id}&arananKelime="
    if source == "aym_bb":
        return f"{AYM_BANK}/BB/{case_no}" if case_no else AYM_BANK
    if source == "aym_norm":
        return f"{AYM_BANK}/ND/{decision_no}" if decision_no else AYM_BANK
    raise ValueError(f"unknown source {source!r}")


def _chamber(source: str, court: str | None) -> str:
    if source == "yargitay":
        return with_institution("yargitay", court)
    if source == "danistay":
        return with_institution("danistay", court)
    if source.startswith("aym"):
        return with_institution("aym", court) if court else institution("aym")
    return (court or "").strip()


def from_dataset_row(row: dict) -> DecisionRecord:
    source = row["source"]
    case_no = (row.get("esas_no") or "").strip() or None
    decision_no = (row.get("karar_no") or "").strip() or None
    raw_date = row.get("karar_tarihi")
    return DecisionRecord(
        id=row["id"],
        source=source,
        chamber=_chamber(source, row.get("court")),
        case_no=case_no,
        decision_no=decision_no,
        decision_date=date.fromisoformat(raw_date) if raw_date else None,
        url=_url(source, row["document_id"], case_no, decision_no),
        text=row["text"],
        raw_sha256=row["raw_sha256"].removeprefix("sha256:"),
    )
