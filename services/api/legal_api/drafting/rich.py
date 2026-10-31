"""A draft as the editor holds it: a document of paragraphs and lists whose text carries
bold, italic, underline and a size, with alignment per paragraph and citation markers as
their own nodes (the editor's JSON, ProseMirror's shape).

The draft's text stays the record (answers, one-click changes and style learning read it);
the editor's document is kept beside it with a fingerprint of the petition it was made
from. While the petition is unchanged, files are made from the document, so what the lawyer
set in the editor reaches Word, PDF and UDF. Once a one-click change rewrites the text, the
document is made again from the text.
"""

from __future__ import annotations

import hashlib
import re

from legal_api.db.drafting_models import Draft
from legal_api.drafting.export import Block, Run, blocks
from legal_api.drafting.style import petition_part, petition_span

MAX_NODES = 20000
_ALIGN_IN = {"left": "left", "center": "centre", "right": "right", "justify": "justify"}
_ALIGN_OUT = {v: k for k, v in _ALIGN_IN.items()}
_SIZE = re.compile(r"^(\d{1,2})(?:pt)?$")


class BadDocument(ValueError):
    pass


def fingerprint(text: str) -> str:
    return hashlib.sha1(petition_part(text).encode()).hexdigest()


# --- text (blocks) to the editor's document ---------------------------------------------

def _text_node(r: Run) -> dict:
    if r.marker:
        return {"type": "citation", "attrs": {"key": r.marker}}
    marks = [{"type": m} for m, on in (("bold", r.bold), ("italic", r.italic),
                                       ("underline", r.underline)) if on]
    if r.size:
        marks.append({"type": "textStyle", "attrs": {"fontSize": f"{r.size}pt"}})
    node: dict = {"type": "text", "text": r.text}
    if marks:
        node["marks"] = marks
    return node


def to_doc(paragraphs: list[Block]) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "attrs": {"textAlign": _ALIGN_OUT.get(b.align, "justify")},
         "content": [_text_node(r) for r in b.runs if r.text or r.marker]}
        for b in paragraphs]}


# --- the editor's document to blocks and text --------------------------------------------

def _size(marks: list[dict]) -> int | None:
    for m in marks:
        if m.get("type") == "textStyle":
            found = _SIZE.match(str((m.get("attrs") or {}).get("fontSize") or ""))
            if found and 6 <= int(found.group(1)) <= 72:
                return int(found.group(1))
    return None


def _runs(nodes: list[dict]) -> list[Run]:
    out = []
    for n in nodes or []:
        kind = n.get("type")
        if kind == "text":
            marks = n.get("marks") or []
            names = {m.get("type") for m in marks}
            out.append(Run(str(n.get("text", "")), bold="bold" in names, italic="italic" in names,
                           underline="underline" in names, size=_size(marks)))
        elif kind == "citation":
            key = str((n.get("attrs") or {}).get("key", ""))
            if re.fullmatch(r"E\d+", key):
                out.append(Run("", marker=key))
        elif kind == "hardBreak":
            out.append(Run(" "))
    return out


def _paragraph(node: dict, prefix: str = "") -> Block:
    align = _ALIGN_IN.get(str((node.get("attrs") or {}).get("textAlign") or ""), "justify")
    runs = _runs(node.get("content") or [])
    if prefix:
        runs.insert(0, Run(prefix))
    return Block(runs, align=align)


def from_doc(doc: dict) -> list[Block]:
    """The document's paragraphs; list items become paragraphs led by "•" or their number."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise BadDocument("not an editor document")
    if _count(doc) > MAX_NODES:
        raise BadDocument("document too large")
    out: list[Block] = []
    for node in doc.get("content") or []:
        kind = node.get("type")
        if kind in ("paragraph", "heading"):
            out.append(_paragraph(node))
        elif kind in ("bulletList", "orderedList"):
            number = int((node.get("attrs") or {}).get("start") or 1)
            for item in node.get("content") or []:
                for i, inner in enumerate(item.get("content") or []):
                    if inner.get("type") != "paragraph":
                        continue
                    lead = ("• " if kind == "bulletList" else f"{number}. ") if i == 0 else ""
                    out.append(_paragraph(inner, lead))
                number += 1
    return out


def _count(node: dict) -> int:
    return 1 + sum(_count(c) for c in node.get("content") or [] if isinstance(c, dict))


def text_of(paragraphs: list[Block]) -> str:
    """Blocks as the draft's text: **bold**, markers as [[E#]], a blank line between
    paragraphs (italics, underline, sizes and alignment live only in the document)."""
    lines = []
    for b in paragraphs:
        parts, bold_open = [], False
        for r in b.runs:
            if r.marker:
                parts.append(("**" if bold_open else "") + f"[[{r.marker}]]")
                bold_open = False
                continue
            if r.bold != bold_open:
                parts.append("**")
                bold_open = r.bold
            parts.append(r.text)
        if bold_open:
            parts.append("**")
        line = "".join(parts).replace("****", "")
        if line.strip():
            lines.append(line.strip())
    return "\n\n".join(lines)


# --- the draft ------------------------------------------------------------------------------

def editor_doc(draft: Draft) -> dict:
    """The document the editor opens: the saved one while the petition is unchanged, else
    one made from the text."""
    doc = draft.meta.get("doc")
    if doc and draft.meta.get("doc_for") == fingerprint(draft.text):
        return doc
    return to_doc(blocks(draft.text, keep_markers=True))


def file_blocks(draft: Draft) -> list[Block]:
    """The paragraphs files are made from."""
    doc = draft.meta.get("doc")
    if doc and draft.meta.get("doc_for") == fingerprint(draft.text):
        return from_doc(doc)
    return blocks(draft.text)


def apply_doc(draft_text: str, doc: dict) -> str:
    """The draft's text with its petition replaced by the document's, the note before it and
    the checklist after it kept."""
    petition = text_of(from_doc(doc))
    start, end = petition_span(draft_text)
    old = draft_text[start:end]
    lead = old[:len(old) - len(old.lstrip())]
    trail = old[len(old.rstrip()):]
    return draft_text[:start] + lead + petition + trail + draft_text[end:]
