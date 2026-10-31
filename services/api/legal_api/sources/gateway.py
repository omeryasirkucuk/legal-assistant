"""Polite HTTP gateway shared by every live source adapter.

Policy (adapted from aydincan/turk-hukuku-ictihat-mcp, MIT):
- The client identifies itself honestly; no browser or official-app impersonation.
- One request at a time per host, with a minimum interval between requests.
- Hard stop on signs of access control (403, 429, captcha, unexpected redirect, HTML where
  JSON was expected): the host is put on cooldown and the request is never retried.
- Other HTTP and network errors raise SourceError without cooldown or retry.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

USER_AGENT = "legal-assistant/0.1 (grounded legal research prototype)"
MIN_INTERVAL_S = 1.0
# Hosts that asked for more room: the decision service answered HTTP 429 to a search followed
# by four fetches at one per second, which put it on cooldown and left answers without case
# law for two minutes (the same question found two decisions in one run and none in the next).
HOST_INTERVAL_S = {"bedesten.adalet.gov.tr": 2.0}
COOLDOWN_S = 120.0
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Structural captcha markers only: decision texts may legitimately contain the word "captcha".
_CAPTCHA = re.compile(
    r'"isDisplayCaptcha"\s*:\s*"?true'
    r'|<[a-z][^>]*\bid\s*=\s*["\']?isDisplayCaptcha\b[^>]*>\s*true\s*<'
    r'|<[a-z][^>]*\bdata-sitekey\s*='
    r'|"FMTE"\s*:\s*"[^"]*DisplayCaptcha'
    r'|reCaptchaTimeout'
    r'|grecaptcha\s*\.\s*(?:render|execute)\s*\(',
    re.IGNORECASE,
)


class SourceError(LookupError):
    """The source returned an error or could not be reached. Not retried."""


class SourceBlocked(SourceError):
    """The source signalled access control. The host is on cooldown for `retry_after` seconds."""

    def __init__(self, message: str, retry_after: float = COOLDOWN_S):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class _HostState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_request: float = float("-inf")
    blocked_until: float = 0.0
    blocked_reason: str = ""


# Rate limits and cooldowns are per host for the whole process: the official services see
# one client, however many answers are being produced at once.
_SHARED_HOSTS: dict[str, _HostState] = {}


class Gateway:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None,
                 min_interval: float = MIN_INTERVAL_S, shared: bool = True):
        self._client = httpx.AsyncClient(
            transport=transport, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        self._hosts: dict[str, _HostState] = _SHARED_HOSTS if shared else {}
        self._min_interval = min_interval

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, *, source: str, expect: str = "json",
                      **kwargs: Any) -> httpx.Response:
        host = urlsplit(url).hostname or url
        state = self._hosts.setdefault(host, _HostState())
        async with state.lock:
            remaining = state.blocked_until - time.monotonic()
            if remaining > 0:
                raise SourceBlocked(f"{source} is on cooldown: {state.blocked_reason}", remaining)
            interval = max(self._min_interval, HOST_INTERVAL_S.get(host, 0.0)) \
                if self._min_interval else 0.0      # tests turn pacing off
            wait = state.last_request + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                raise SourceError(f"{source} timed out") from exc
            except httpx.TransportError as exc:
                raise SourceError(f"{source} unreachable: {exc}") from exc
            finally:
                state.last_request = time.monotonic()
            try:
                _check_access(response, source, expect)
            except SourceBlocked as exc:
                state.blocked_reason = str(exc)
                state.blocked_until = time.monotonic() + exc.retry_after
                raise
        if not response.is_success:
            raise SourceError(f"{source} returned HTTP {response.status_code}")
        return response

    async def json(self, method: str, url: str, *, source: str, **kwargs: Any) -> Any:
        response = await self.request(method, url, source=source, expect="json", **kwargs)
        try:
            return response.json()
        except ValueError:
            raise SourceError(f"{source} returned invalid JSON") from None


def _check_access(response: httpx.Response, source: str, expect: str) -> None:
    status = response.status_code
    if status == 429:
        header = (response.headers.get("retry-after") or "").strip()
        raise SourceBlocked(f"{source} rate limit (HTTP 429)",
                            float(header) if header.isdigit() else COOLDOWN_S)
    if status == 403:
        raise SourceBlocked(f"{source} refused the request (HTTP 403)")
    if 300 <= status < 400:
        raise SourceBlocked(f"{source} redirected unexpectedly (HTTP {status})")
    content_type = (response.headers.get("content-type") or "").lower()
    if any(t in content_type for t in ("pdf", "octet-stream", "image/")):
        return
    body = response.text
    if _CAPTCHA.search(body):
        raise SourceBlocked(f"{source} asked for a captcha")
    looks_html = "html" in content_type or body.lstrip().startswith("<")
    if expect == "json" and response.is_success and looks_html:
        raise SourceBlocked(f"{source} returned an HTML page instead of JSON")
