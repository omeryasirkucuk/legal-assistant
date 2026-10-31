"""Attachments as material for an answer: their text, and images shown as images.

The lawyer's documents describe the case (a notice, a contract, a decision they received);
they are given to the understanding step as an excerpt and to the writer in full, but they
are not legal sources and are not cited as such.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

UNDERSTAND_CHARS = 6000       # per document, for working out the task and the issues
WRITE_CHARS = 40000           # per document, for the writer
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 5


@dataclass(frozen=True)
class Attachment:
    name: str
    media_type: str
    text: str
    image: bytes | None = None      # only for images the model can view


def _doc(a: Attachment, chars: int) -> str:
    body = a.text[:chars] if a.text else "(içeriği okunamadı)"
    return f"<attached_document name=\"{a.name}\">\n{body}\n</attached_document>"


def for_understanding(message: str, attachments: list[Attachment]) -> str:
    if not attachments:
        return message
    docs = [_doc(a, UNDERSTAND_CHARS) for a in attachments if a.image is None]
    images = [a.name for a in attachments if a.image is not None]
    parts = [message, "<attachments>", *docs]
    if images:
        parts.append("Eklenen görseller: " + ", ".join(images))
    parts.append("</attachments>")
    return "\n\n".join(parts)


def for_writer(attachments: list[Attachment]) -> list[dict]:
    blocks: list[dict] = []
    images = 0
    for a in attachments:
        if a.image is not None and a.media_type in IMAGE_TYPES and images < MAX_IMAGES \
                and len(a.image) <= MAX_IMAGE_BYTES:
            images += 1
            blocks.append({"type": "text", "text": f"Eklenen görsel: {a.name}"})
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": a.media_type,
                "data": base64.b64encode(a.image).decode()}})
        elif a.image is None:
            blocks.append({"type": "text", "text": _doc(a, WRITE_CHARS)})
    if blocks:
        blocks.insert(0, {"type": "text", "text": (
            "Avukatın eklediği belgeler aşağıdadır: vakanın malzemesidir, hukuki kaynak "
            "değildir; olguları buradan al, hukuki dayanağı belgelerden (kaynaklardan) göster.")})
    return blocks
