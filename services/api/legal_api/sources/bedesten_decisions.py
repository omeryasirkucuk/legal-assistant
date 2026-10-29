"""Court decisions from the Ministry of Justice Bedesten service.

One service covers the Court of Cassation, Council of State, regional appeal courts,
first-instance civil courts and appeals in the interest of law.

  POST /emsal-karar/searchDocuments  {"data": {phrase, itemTypeList, pageSize, pageNumber},
                                      "paging": true}
  POST /emsal-karar/getDocumentContent {"data": {"documentId": ID}} -> base64 HTML
Public page for any document: https://mevzuat.adalet.gov.tr/ictihat/<id>
"""

from __future__ import annotations

import base64

from legal_api.locale import with_institution
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.query import to_and_query
from legal_api.sources.text import html_to_text
from legal_api.sources.types import Court, Decision, DecisionRef

BASE = "https://bedesten.adalet.gov.tr/emsal-karar"
PUBLIC_PAGE = "https://mevzuat.adalet.gov.tr/ictihat"
SOURCE = "Bedesten"
MAX_PAGE_SIZE = 20

ITEM_TYPES: dict[Court, str] = {
    Court.YARGITAY: "YARGITAYKARARI",
    Court.DANISTAY: "DANISTAYKARAR",
    Court.ISTINAF: "ISTINAFHUKUK",
    Court.YEREL: "YERELHUKUK",
    Court.KYB: "KYB",
}
_COURT_BY_ITEM = {v: k for k, v in ITEM_TYPES.items()}
_INSTITUTION = {Court.YARGITAY: "yargitay", Court.DANISTAY: "danistay"}


class BedestenDecisions:
    def __init__(self, gateway: Gateway):
        self._gw = gateway

    async def _post(self, endpoint: str, data: dict, paging: bool = False) -> dict:
        body: dict = {"data": data}
        if paging:
            body["paging"] = True
        reply = await self._gw.json("POST", f"{BASE}/{endpoint}", source=SOURCE, json=body)
        meta = reply.get("metadata") or {}
        if meta.get("FMTY") == "ERROR":
            raise SourceError(f"{SOURCE}: {meta.get('FMTE', 'error')}")
        return reply.get("data") or {}

    async def search(self, phrase: str, courts: list[Court] | None = None, page: int = 1,
                     size: int = 10) -> tuple[int, list[DecisionRef]]:
        courts = courts or [Court.YARGITAY]
        data = await self._post("searchDocuments", {
            "phrase": to_and_query(phrase),
            "itemTypeList": [ITEM_TYPES[c] for c in courts],
            "pageSize": max(1, min(size, MAX_PAGE_SIZE)),
            "pageNumber": max(1, page),
        }, paging=True)
        refs = [self._ref(item) for item in data.get("emsalKararList") or []]
        return int(data.get("total") or 0), refs

    async def fetch(self, ref: DecisionRef) -> Decision:
        """Full text for a search hit. Takes the ref, not a bare id, so the citation metadata
        always comes from the source's own listing."""
        doc_id = ref.source_id.split(":", 1)[-1]
        data = await self._post("getDocumentContent", {"documentId": doc_id})
        content = data.get("content")
        if not content or "html" not in (data.get("mimeType") or "text/html"):
            raise SourceError(f"{SOURCE}: no text for document {doc_id}")
        text = html_to_text(base64.b64decode(content).decode("utf-8", "replace"))
        return Decision(ref=ref, text=text)

    @staticmethod
    def _ref(item: dict) -> DecisionRef:
        doc_id = str(item.get("documentId", ""))
        court = _COURT_BY_ITEM.get((item.get("itemType") or {}).get("name", ""), Court.YARGITAY)
        chamber = (item.get("birimAdi") or "").strip()
        if court in _INSTITUTION:
            chamber = with_institution(_INSTITUTION[court], chamber)
        iso = (item.get("kararTarihiStr") or "").strip()
        if len(iso) == 10 and iso[2] == ".":
            iso = f"{iso[6:]}-{iso[3:5]}-{iso[:2]}"
        return DecisionRef(
            source_id=f"bedesten:{doc_id}",
            court=court,
            chamber=chamber,
            case_no=item.get("esasNo") or None,
            decision_no=item.get("kararNo") or None,
            decision_date=iso or None,
            url=f"{PUBLIC_PAGE}/{doc_id}",
        )
