"""One-click changes to a draft: shorter, longer, plainer, more formal.

The draft (or the selected passage) is rewritten with its citation markers and bracketed
placeholders kept; a rewrite that invents a marker is rejected, since the markers
are what tie the petition's legal reasons to their sources.
"""

from __future__ import annotations

import re

from legal_api import llm
from legal_api.prompts import prompt

MAX_TOKENS = 16000
_MARKER = re.compile(r"\[\[E\d+\]\]")
_SEPARATOR = re.compile(r"^\s*---\s*$", re.MULTILINE)


class RewriteRejected(RuntimeError):
    pass


def markers(text: str) -> set[str]:
    return set(_MARKER.findall(text))


async def rewrite(text: str, action: str, rules: list[str], usage: llm.Usage) -> str:
    system = prompt("draft_adjust").replace("{action}", prompt(f"draft_action_{action}"))
    if rules:
        system += "\n" + "\n".join(f"- {r}" for r in rules)
    response = await llm.create("write", usage, "draft_adjust", max_tokens=MAX_TOKENS,
                                system=system,
                                messages=[{"role": "user", "content": text}])
    out = "".join(b.text for b in response.content if b.type == "text").strip()
    if not out or markers(out) - markers(text):
        raise RewriteRejected("the rewrite changed the citation markers")
    # The dashes set the petition off from the note and checklist; one lost put the
    # checklist into the petition file.
    if len(_SEPARATOR.findall(out)) != len(_SEPARATOR.findall(text)):
        raise RewriteRejected("the rewrite changed the petition's boundaries")
    return out
