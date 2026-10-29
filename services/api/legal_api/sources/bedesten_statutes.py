"""Current legislation, article by article, from the Bedesten legislation service.

  POST /mevzuat/searchDocuments    {"data": {mevzuatAdi | phrase, pageSize<=20, pageNumber},
                                    "paging": true}
  POST /mevzuat/mevzuatMaddeTree   {"data": {"mevzuatId": ID}}  -> nested article tree
  POST /mevzuat/getDocumentContent {"data": {"documentType": "MADDE", "id": ARTICLE_ID}}
                                    -> base64 HTML of one article (current consolidated text)
Covers laws, decree-laws, presidential decrees and regulations, by-laws, communiques, etc.
"""

from __future__ import annotations

import base64
import re

from legal_api.grounding.normalize import tr_lower
from legal_api.locale import statute_term
from legal_api.sources.cache import TTLCache
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.text import html_to_text
from legal_api.sources.types import Article, StatuteRef

BASE = "https://bedesten.adalet.gov.tr/mevzuat"
SOURCE = "Bedesten legislation"
MAX_PAGE_SIZE = 20

# Shared by every request in the process: statutes change rarely.
_cache = TTLCache()


class BedestenStatutes:
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

    async def search(self, *, title: str | None = None, phrase: str | None = None,
                     number: str | None = None, page: int = 1,
                     size: int = 10) -> tuple[int, list[StatuteRef]]:
        if not (title or phrase or number):
            raise ValueError("title, phrase or number is required")
        query: dict = {"pageSize": max(1, min(size, MAX_PAGE_SIZE)), "pageNumber": max(1, page)}
        if number:
            query["mevzuatNo"] = number
        if title:
            query["mevzuatAdi"] = title
        if phrase:
            query["phrase"] = phrase
        data = await _cache.get(("search", tuple(sorted(query.items()))),
                                lambda: self._post("searchDocuments", query, paging=True))
        refs = [self._ref(item) for item in data.get("mevzuatList") or []]
        return int(data.get("total") or 0), refs

    async def _nodes(self, statute: StatuteRef) -> list[dict]:
        tree = await _cache.get(("tree", statute.statute_id), lambda: self._post(
            "mevzuatMaddeTree", {"mevzuatId": statute.statute_id}))
        nodes, stack = [], list(tree.get("children") or [])
        while stack:
            node = stack.pop()
            if node.get("maddeId"):
                nodes.append(node)
            stack.extend(node.get("children") or [])
        return nodes

    async def article_index(self, statute: StatuteRef) -> dict[int, str]:
        """Map of article number -> article id, flattened from the article tree."""
        index: dict[int, str] = {}
        for node in await self._nodes(statute):
            number = node.get("maddeNo")
            if isinstance(number, int) and number not in index:
                index[number] = str(node["maddeId"])
        return index

    async def _resolve(self, statute: StatuteRef, label: str) -> tuple[str, str] | None:
        """(article id, display label) for labels like "315", "269/a", "ek 1", "gecici 3".

        Lettered articles ("269/a") are published inside their base article's text, so they
        resolve to the base article. Additional and temporary articles are matched by title.
        """
        ref = parse_article_label(label)
        if ref is None:
            return None
        kind, number, display = ref
        if kind == "main":
            article_id = (await self.article_index(statute)).get(number)
            return (article_id, display) if article_id else None
        word = tr_lower(statute_term(kind))
        for node in await self._nodes(statute):
            title = tr_lower(f"{node.get('maddeBaslik') or ''} {node.get('title') or ''}")
            if re.search(rf"\b{word}\s+{statute_term('article')}\s*{number}\b", title):
                return str(node["maddeId"]), display
        return None

    async def article(self, statute: StatuteRef, label: int | str) -> Article | None:
        """Current text of one article, or None if the statute has no such article."""
        resolved = await self._resolve(statute, str(label))
        if resolved is None:
            return None
        article_id, display = resolved
        data = await _cache.get(("article", article_id), lambda: self._post(
            "getDocumentContent", {"documentType": "MADDE", "id": article_id}))
        content = data.get("content")
        if not content:
            raise SourceError(f"{SOURCE}: no text for article {article_id}")
        text = html_to_text(base64.b64decode(content).decode("utf-8", "replace"))
        return Article(statute=statute, article_id=article_id, number=display, text=text,
                       updated_at=None, url=statute.url)

    @staticmethod
    def _ref(item: dict) -> StatuteRef:
        kind = (item.get("mevzuatTur") or {}).get("name") or ""
        return StatuteRef(
            statute_id=str(item.get("mevzuatId", "")),
            number=str(item.get("mevzuatNo", "")),
            title=(item.get("mevzuatAdi") or "").strip(),
            kind=kind,
            gazette_no=item.get("resmiGazeteSayisi") or None,
            url=item.get("url") or "https://www.mevzuat.gov.tr",
        )


def parse_article_label(label: str) -> tuple[str, int, str] | None:
    """("main" | "additional" | "temporary", number, display label) from a free-form label."""
    text = tr_lower(label).replace(statute_term("article"), " ").replace("m.", " ").strip()
    for kind in ("additional", "temporary"):
        word = tr_lower(statute_term(kind))
        m = re.match(rf"^{word}\s*(\d+)$", text)
        if m:
            return kind, int(m.group(1)), f"{statute_term(kind)} {m.group(1)}"
    m = re.match(r"^(\d+)\s*(?:/\s*(\w))?$", text)
    if not m:
        return None
    display = f"{m.group(1)}/{m.group(2)}" if m.group(2) else m.group(1)
    return "main", int(m.group(1)), display
