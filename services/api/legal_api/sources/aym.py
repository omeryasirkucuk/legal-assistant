"""Constitutional Court decisions (individual applications and norm review).

Source: AYM decision bank JSON API (adapted from aydincan/turk-hukuku-ictihat-mcp, MIT).
  POST /api/core/public/search
    search:    {"kararTipi": T, "query": Q, "page": N, "size": N}
    full text: {"kararTipi": T, "id": UUID, "page": 1, "size": 1} -> record["icerik"] (HTML)
The bank's document-download endpoint requires a human captcha token; it is never called.
"""

from __future__ import annotations

import json
import re

from legal_api.locale import institution
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.query import to_and_query
from legal_api.sources.text import html_to_text
from legal_api.sources.types import Court, Decision, DecisionRef

BASE = "https://kararlarbilgibankasi.anayasa.gov.tr"
API = f"{BASE}/api/core/public/search"
SOURCE = "AYM decision bank"
_KIND = {Court.AYM_BIREYSEL: "BireyselBasvuru", Court.AYM_NORM: "NormDenetimi"}
_HEADERS = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}


class AymDecisions:
    def __init__(self, gateway: Gateway):
        self._gw = gateway

    async def _post(self, payload: dict) -> dict:
        # The API rejects some escaped payloads; send raw UTF-8.
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return await self._gw.json("POST", API, source=SOURCE, content=body, headers=_HEADERS)

    async def search(self, phrase: str, court: Court = Court.AYM_BIREYSEL, page: int = 1,
                     size: int = 10) -> tuple[int, list[DecisionRef]]:
        data = await self._post({"kararTipi": _KIND[court], "query": to_and_query(phrase),
                                 "page": max(1, page), "size": max(1, min(size, 20))})
        records = data.get("data") or []
        return int(data.get("total") or len(records)), [_ref(r, court) for r in records]

    async def fetch(self, ref: DecisionRef) -> Decision:
        uuid = ref.source_id.split(":", 1)[-1]
        data = await self._post({"kararTipi": _KIND[ref.court], "id": uuid, "page": 1, "size": 1})
        records = data.get("data") or []
        text = html_to_text((records[0] if records else {}).get("icerik") or "")
        if len(text) < 60:
            raise SourceError(f"{SOURCE}: no text for {uuid}")
        return Decision(ref=ref, text=text)


def _iso(value: str | None) -> str | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value or "")
    return m.group(1) if m else None


def _ref(record: dict, court: Court) -> DecisionRef:
    uuid = str(record.get("id") or "")
    if court is Court.AYM_BIREYSEL:
        application_no = (record.get("basvuruNo") or "").strip()
        return DecisionRef(
            source_id=f"aym:{uuid}", court=court, chamber=institution("aym"),
            case_no=application_no or None, decision_no=None,
            decision_date=_iso(record.get("kararTarihi")),
            url=f"{BASE}/BB/{application_no}" if application_no else BASE,
        )
    decision_no = (record.get("kararNo") or "").strip()
    return DecisionRef(
        source_id=f"aym:{uuid}", court=court, chamber=institution("aym"),
        case_no=(record.get("esasNo") or "").strip() or None, decision_no=decision_no or None,
        decision_date=_iso(record.get("kararTarihi")),
        url=f"{BASE}/ND/{decision_no}" if decision_no else BASE,
    )
