"""Search-phrase normalisation for the official search services.

Bedesten and the AYM decision bank OR plain words together, so "kira tahliye" would match
hundreds of thousands of decisions. `to_and_query` turns free text into a query those
services treat as AND. Ported from aydincan/turk-hukuku-ictihat-mcp (MIT):

- words and quoted phrases become required (`+`); a leading `-` excludes and is kept;
- suffixes after an apostrophe are dropped ("TMK'nin" -> "TMK"), otherwise the suffix becomes
  a separate required word;
- explicit AND / OR / NOT (and lowercase and / or) are respected; lowercase "not" is a
  Turkish word, not an operator;
- characters other than letters, digits, spaces, quotes, + and - become spaces.
"""

from __future__ import annotations

import re

_OPERATORS = {"AND", "OR", "NOT"}
_LOWER_OPERATORS = {"and", "or"}
_TOKEN = re.compile(r'([+-]?)("[^"]*"|[^\s"]+)')


def _operator(sign: str, body: str) -> str | None:
    if sign:
        return None
    if body in _OPERATORS:
        return body
    if body in _LOWER_OPERATORS:
        return body.upper()
    return None


def to_and_query(text: str) -> str:
    s = re.sub(r"['’‘`´]\w*", "", text or "")
    s = re.sub(r'[^\w\s"+\-]|_', " ", s)
    if s.count('"') % 2:
        s = s.replace('"', " ")

    parts: list[tuple[str, str]] = []
    for sign, body in _TOKEN.findall(s):
        if body.startswith('"'):
            inner = " ".join(re.sub(r"[+\-]", " ", body[1:-1]).split())
            if inner:
                parts.append((sign, f'"{inner}"'))
            continue
        for i, word in enumerate(w for w in re.split(r"[+\-]+", body) if w):
            parts.append((sign if i == 0 else "", word))

    if any(_operator(sign, body) for sign, body in parts):
        out: list[str] = []
        for sign, body in parts:
            op = _operator(sign, body)
            if op:
                if out and out[-1] not in _OPERATORS:
                    out.append(op)
            else:
                out.append(sign + body)
        while out and out[-1] in _OPERATORS:
            out.pop()
    else:
        out = [(sign or "+") + body for sign, body in parts]

    if not out:
        raise ValueError("search phrase must contain letters or digits")
    return " ".join(out)
