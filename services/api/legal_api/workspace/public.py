"""Discovery sends only terms from a public legal vocabulary. Citations come from fetched texts."""

from __future__ import annotations

import asyncio
import hashlib
import re
from functools import cache
from urllib.parse import parse_qs, urlsplit, urlunsplit

from legal_api.config import REPO_ROOT, get_settings
from legal_api.files.extract import text_of
from legal_api.sources.gateway import Gateway, SourceError
from legal_api.sources.text import html_to_text

SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
HOSTS = (
    "resmigazete.gov.tr", "mevzuat.gov.tr", "mevzuat.adalet.gov.tr",
    "kararlarbilgibankasi.anayasa.gov.tr", "karararama.yargitay.gov.tr", "cdn.tbmm.gov.tr",
    "tuketici.ticaret.gov.tr",
)
MAX_BYTES = 8 * 1024 * 1024
CHARSET = re.compile(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", re.IGNORECASE)


def readable_html(content: bytes, content_type: str) -> str:
    declared = CHARSET.search(content_type.encode("ascii", "ignore")) or CHARSET.search(content[:8192])
    encoding = declared.group(1).decode("ascii").lower() if declared else "utf-8"
    if encoding not in ("utf-8", "utf8", "windows-1254", "iso-8859-9", "windows-1252"):
        encoding = "utf-8"
    return " ".join(html_to_text(content.decode(encoding, errors="replace")).split())


@cache
def vocabulary() -> frozenset[str]:
    return frozenset((REPO_ROOT / "locales/tr/public_legal_terms.txt").read_text().split())


def public_query(text: str) -> str:
    words = re.findall(r"[a-zçğıöşü]+", text.translate(str.maketrans("Iİ", "ıi")).lower())
    return " ".join(dict.fromkeys(word for word in words if word in vocabulary()))


def official_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").removeprefix("www.")
        if parsed.scheme != "https" or host not in HOSTS or parsed.username is not None \
                or parsed.password is not None or parsed.port not in (None, 443):
            return None
        # Official legislation permalinks also use a three-field numeric identifier.
        if host == "mevzuat.gov.tr" and parsed.path.lower() == "/mevzuat":
            params = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
            keys = ("mevzuattur", "mevzuattertip", "mevzuatno")
            if not all(len(params.get(k, [])) == 1 and re.fullmatch(r"[0-9]{1,8}", params[k][0])
                       for k in keys):
                return None
            filename = ".".join(params[k][0] for k in keys)
            return f"https://www.mevzuat.gov.tr/MevzuatMetin/{filename}.pdf"
        if not re.fullmatch(r"/[A-Za-z0-9_./%~-]{2,400}", parsed.path):
            return None
        return urlunsplit(("https", parsed.netloc.lower(), parsed.path, "", ""))
    except ValueError:
        return None


class PublicResearch:
    def __init__(self, gateway: Gateway):
        self.gateway = gateway
        self.links: dict[str, tuple[str, str]] = {}

    @property
    def enabled(self) -> bool:
        settings = get_settings()
        return not settings.protected_data and bool(settings.brave_search_api_key)

    async def search(self, query: str) -> list[dict]:
        settings = get_settings()
        safe_query = public_query(query)
        if not self.enabled or not safe_query:
            return []
        data = await self.gateway.json(
            "GET", SEARCH_URL, source="Brave Search",
            headers={"X-Subscription-Token": settings.brave_search_api_key},
            params={"q": safe_query + " (" + " OR ".join(f"site:{host}" for host in HOSTS) + ")",
                    "country": "TR", "search_lang": "tr", "count": 15},
        )
        found = []
        for item in (data.get("web") or {}).get("results") or []:
            url = official_url(item.get("url", ""))
            if not url:
                continue
            title = html_to_text(item.get("title", ""))[:180] or urlsplit(url).hostname
            key = f"W{len(self.links) + 1}"
            self.links[key] = (url, title)
            found.append({"id": key, "title": title, "url": url})
        return found

    def user_references(self, message: str) -> list[dict]:
        links = dict.fromkeys(re.findall(r"https://[^\s<>\][)(]+", message))
        found = []
        for url in list(links)[:8]:
            approved = official_url(url.rstrip(".,;"))
            if approved:
                key = f"U{len(found) + 1}"
                self.links[key] = (approved, f"Resmî belge · {urlsplit(approved).hostname}")
                found.append({"id": key, "url": approved})
        return found

    def register_reference(self, key: str, url: str, title: str) -> None:
        resolved = official_url(url)
        if not resolved:
            raise ValueError("Kaynak okunabilir bir resmî belge adresi içermiyor.")
        self.links[key] = (resolved, title)

    async def read(self, key: str) -> tuple[str, str, str, str]:
        if get_settings().protected_data or key not in self.links:
            raise ValueError("Kamu kaynağı için önce arama yap.")
        url, title = self.links[key]
        res = await self.gateway.request("GET", url, source=urlsplit(url).hostname, expect="text",
                                         max_bytes=MAX_BYTES)
        kind = res.headers.get("content-type", "")
        try:
            if "pdf" in kind or res.content[:5] == b"%PDF-":
                body = await asyncio.to_thread(text_of, "source.pdf", res.content)
            elif "html" in kind or "text" in kind:
                body = readable_html(res.content, kind)
            else:
                raise ValueError("Kamu kaynağının metin biçimi desteklenmiyor.")
        except Exception as exc:
            raise SourceError("Kamu kaynağının metni okunamadı.") from exc
        if not body.strip() or len(body) > 1000000:
            raise SourceError("Kamu kaynağının metni okunamadı veya fazla uzun.")
        return url, title, body, hashlib.sha256(res.content).hexdigest()
