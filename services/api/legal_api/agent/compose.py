"""The short answer: one line per branch, built from the cited sub-answers.

The sub-answers stay as they are (cited, shown under "details"). A cheap call writes, for
every sub-answer of a branch, its gist in a few words ("5 days, from service"); code joins a branch's
gists into its line, so no sub-answer can be left out of the short answer (a single line
written freely did leave the second period of a branch out). Citation keys come from the
sub-answers, never from the model. A gist that states a number its sub-answer does not is
replaced by the sub-answer itself.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from legal_api import llm
from legal_api.config import get_settings
from legal_api.grounding.normalize import tr_capitalize, tr_fold
from legal_api.grounding.numbers import digits_for_quantities, numbers_in, unsupported_numbers
from legal_api.locale import message
from legal_api.prompts import prompt

MAX_GIST_CHARS = 220
SAME_GIST_OVERLAP = 0.5

_SCHEMA = {
    "type": "object",
    "properties": {
        "gists": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "branch": {"type": "string"},
                    "atom": {"type": "string"},
                    "gist": {"type": "string"},
                },
                "required": ["branch", "atom", "gist"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["gists"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Line:
    branch: int
    text: str
    keys: tuple[str, ...]
    composed: bool          # False: every gist fell back to its sub-answer


def _atom_text(atom: dict) -> str:
    return "".join(s["text"] for s in atom["segments"]).strip()


def _atom_keys(atoms: list[dict]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(k for a in atoms for s in a["segments"] for k in s["keys"]))


def _listing(structure: dict) -> str:
    blocks = []
    for i, branch in enumerate(structure["branches"]):
        found = [(j, a) for j, a in enumerate(branch["atoms"]) if a["found"]]
        if not found:
            continue
        lines = [f"[B{i + 1}] {branch['label']}"]
        lines += [f"  [A{j + 1}] {a['ask']} -> {_atom_text(a)}" for j, a in found]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def tag_index(tag: str, prefix: str, names: list[str] | None = None) -> int | None:
    """0-based index from a tag the model wrote: "B2", "[B2]", "2", or the item's name."""
    clean = tag.strip().strip("[]").strip()
    m = re.fullmatch(rf"(?:{prefix})?\s*(\d+)", clean, re.IGNORECASE)
    if m:
        return int(m.group(1)) - 1
    if names:
        folded = tr_fold(clean)
        for i, name in enumerate(names):
            if tr_fold(name) == folded or tr_fold(name).startswith(folded):
                return i
    return None


def _gist_ok(gist: str, atom: dict) -> bool:
    return bool(gist) and len(gist) <= MAX_GIST_CHARS and not unsupported_numbers(
        gist, [_atom_text(atom)])


def _same_gist(a: str, b: str) -> bool:
    """Two gists that state the same numbers in mostly the same words (two sub-answers
    citing one sentence of the same article)."""
    if numbers_in(a) != numbers_in(b):
        return False
    wa, wb = set(tr_fold(a).split()), set(tr_fold(b).split())
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= SAME_GIST_OVERLAP


def _line(i: int, branch: dict, gists: dict[int, str]) -> Line | None:
    found = [(j, a) for j, a in enumerate(branch["atoms"]) if a["found"]]
    if not found:
        return None
    parts, composed = [], False
    for j, atom in found:
        gist = " ".join(gists.get(j, "").split()).rstrip(".;")
        if _gist_ok(gist, atom):
            composed = True
        else:
            gist = _atom_text(atom).rstrip(".;")
        if not any(_same_gist(gist, p) for p in parts):
            parts.append(gist)
    # Quantities as digits throughout, whether a gist or a sub-answer supplied them.
    text = digits_for_quantities(f"{tr_capitalize(branch['label'])}: {'; '.join(parts)}")
    return Line(i, text, _atom_keys([a for _, a in found]), composed)


async def compose_branch(question: str, structure: dict, i: int, usage: llm.Usage,
                         instruction: str | None = None) -> Line | None:
    """The line of branch `i`, written as soon as that branch's sub-answers are in, so the
    short answer can be shown branch by branch while the others are still being answered."""
    branch = structure["branches"][i]
    if not any(a["found"] for a in branch["atoms"]):
        return None
    listing = _listing({"branches": [branch]})
    content = f"<question>{question}</question>\n"
    if instruction:
        content += f"<instruction>{instruction}</instruction>\n"
    content += f"\n<sub_answers>\n{listing}\n</sub_answers>"
    response = await llm.create(
        "cheap", usage, "compose", max_tokens=4000, system=prompt("compose"),
        messages=[{"role": "user", "content": content}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    gists: dict[int, str] = {}
    for item in json.loads(text)["gists"] if text else []:
        j = tag_index(item["atom"], "A")
        if j is not None and 0 <= j < len(branch["atoms"]):
            gists.setdefault(j, item["gist"])
    return _line(i, branch, gists)


async def compose(question: str, structure: dict, usage: llm.Usage,
                  instruction: str | None = None) -> list[Line]:
    lines = await asyncio.gather(*(compose_branch(question, structure, i, usage, instruction)
                                   for i in range(len(structure["branches"]))))
    return [ln for ln in lines if ln]


def short_text(lines: list[Line]) -> str:
    """One bullet per line, citation markers after the text; a plain statement that nothing
    was found when no branch has a cited answer."""
    if not lines:
        return message("status", "no_answer")
    out = []
    for line in lines:
        markers = "".join(f" [[{k}]]" for k in line.keys if f"[[{k}]]" not in line.text)
        out.append(f"- {line.text}{markers}")
    return "\n".join(out)


def lines_data(lines: list[Line]) -> list[dict]:
    return [{"branch": ln.branch, "text": ln.text, "keys": list(ln.keys),
             "composed": ln.composed} for ln in lines]
