"""A case file's documents as material for a question asked in it.

When the file's documents are short they go whole; otherwise each is cut into paragraph
chunks and only the chunks nearest the question (by the local embedding model, so no
model call is spent) go, in their document order, so the answer can draw on a report or
the other side's petition without the lawyer attaching it again.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass

from legal_api.corpus.chunking import chunk_text
from legal_api.embeddings import embed_passages, embed_query
from legal_api.files.context import Attachment
from legal_api.locale import matter_terms

WHOLE_CHARS = 12000      # all documents together below this go whole
PASSAGE_CHARS = 10000    # otherwise, at most this much of the nearest chunks
MAX_PASSAGES = 8
_CACHE_FILES = 200


@dataclass(frozen=True)
class Document:
    id: uuid.UUID
    name: str
    text: str


_vectors: OrderedDict[tuple[uuid.UUID, int], list[tuple[str, list[float]]]] = OrderedDict()


def _chunks(doc: Document) -> list[tuple[str, list[float]]]:
    """A document's chunks with their vectors, computed once per document version."""
    key = (doc.id, len(doc.text))
    if key in _vectors:
        _vectors.move_to_end(key)
        return _vectors[key]
    texts = [c.text for c in chunk_text(doc.text)]
    pairs = list(zip(texts, embed_passages(texts), strict=True)) if texts else []
    _vectors[key] = pairs
    if len(_vectors) > _CACHE_FILES:
        _vectors.popitem(last=False)
    return pairs


def material(question: str, docs: list[Document]) -> list[Attachment]:
    """Blocking (embeds); call it off the event loop."""
    docs = [d for d in docs if d.text and d.text.strip()]
    if not docs:
        return []
    t = matter_terms()
    if sum(len(d.text) for d in docs) <= WHOLE_CHARS:
        return [Attachment(t["document_name"].format(name=d.name), "text/plain", d.text) for d in docs]

    q = embed_query(question)
    scored = []
    for d in docs:
        for i, (text, v) in enumerate(_chunks(d)):
            scored.append((sum(a * b for a, b in zip(q, v, strict=True)), d.id, i, text))
    scored.sort(key=lambda s: s[0], reverse=True)
    chosen: dict[uuid.UUID, list[tuple[int, str]]] = {}
    total = 0
    for _, doc_id, i, text in scored[:MAX_PASSAGES]:
        if total + len(text) > PASSAGE_CHARS:
            continue
        chosen.setdefault(doc_id, []).append((i, text))
        total += len(text)
    out = []
    for d in docs:
        if d.id in chosen:
            parts = [text for _, text in sorted(chosen[d.id])]
            out.append(Attachment(t["document_parts"].format(name=d.name), "text/plain",
                                  f"\n\n{t['gap']}\n\n".join(parts)))
    return out
