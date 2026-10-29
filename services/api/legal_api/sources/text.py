"""HTML-to-plain-text conversion that keeps paragraph boundaries."""

from __future__ import annotations

import html
import re


def html_to_text(raw: str, *, double_escaped: bool = False) -> str:
    s = html.unescape(raw) if double_escaped else raw
    s = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_tags_inline(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(raw or ""))).strip()
