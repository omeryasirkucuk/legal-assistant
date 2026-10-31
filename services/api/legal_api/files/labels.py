"""What a stored file is, for filtering the lawyer's files: its format, the kind of document
(petition, court decision, contract, ...) and the area of law it concerns (labour, tenancy, ...).

The format comes from the file name. Kind and area come from the text already read from the
file, scored against a weighted word list (locales/tr/document_labels.json): no model call, so
labelling costs nothing and takes a few milliseconds. A kind's title words (the word for
"notice" heading a notice) count only near the top of the document, where titles stand; an
area's words count by how often they occur (up to three times), so the matter the document
is about outweighs a passing mention. A file with no clear winner is labelled "other".
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from legal_api.grounding.normalize import tr_fold
from legal_api.locale import document_labels

OTHER = "other"
HEAD_CHARS = 800
SCAN_CHARS = 12000
MIN_KIND = 4
MIN_AREA = 4
MAX_REPEATS = 3

FORMATS = {
    "word": (".docx", ".doc", ".odt", ".rtf"),
    "pdf": (".pdf",),
    "udf": (".udf",),
    "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tif", ".tiff"),
    "spreadsheet": (".xlsx", ".xls", ".ods", ".csv"),
    "email": (".eml", ".msg"),
    "text": (".txt", ".md", ".html", ".htm", ".xml", ".json"),
}
# What the system makes from each petition type (drafting.types ids).
DRAFT_KINDS = {"ihtarname": "notice"}


def file_format(name: str, media_type: str = "") -> str:
    suffix = Path(name).suffix.lower()
    for fmt, suffixes in FORMATS.items():
        if suffix in suffixes:
            return fmt
    return "image" if media_type.startswith("image/") else OTHER


def _pattern(word: str) -> re.Pattern[str]:
    # A word must start a token; Turkish suffixes may follow it.
    return re.compile(r"(?<!\w)" + re.escape(tr_fold(word)))


def _head_body(groups: dict) -> dict:
    return {k: ({_pattern(w): n for w, n in v["head"].items()},
                {_pattern(w): n for w, n in v["body"].items()}) for k, v in groups.items()}


@cache
def _lexicon() -> tuple[dict, dict]:
    raw = document_labels()
    kinds = _head_body(raw["kinds"])
    areas = {a: {_pattern(w): n for w, n in words.items()} for a, words in raw["areas"].items()}
    return kinds, areas


def _best(scores: dict[str, int], minimum: int) -> str:
    label, score = max(scores.items(), key=lambda kv: kv[1], default=(OTHER, 0))
    return label if score >= minimum else OTHER


def _scored(text: str, groups: dict) -> dict[str, int]:
    folded = tr_fold(text[:SCAN_CHARS])
    head = folded[:HEAD_CHARS]
    return {label: sum(n for p, n in heads.items() if p.search(head))
            + sum(n for p, n in body.items() if p.search(folded))
            for label, (heads, body) in groups.items()}


def document_kind(text: str) -> str:
    return _best(_scored(text, _lexicon()[0]), MIN_KIND)


def legal_area(text: str, minimum: int = MIN_AREA) -> str:
    folded = tr_fold(text[:SCAN_CHARS])
    _, areas = _lexicon()
    return _best({area: sum(n * min(len(p.findall(folded)), MAX_REPEATS) for p, n in words.items())
                  for area, words in areas.items()}, minimum)


def labels(name: str, text: str, petition_type: str | None = None) -> tuple[str, str]:
    """(kind, area) of a file from its name and text. The name is read as the first line, since
    lawyers name files by what they are (an eviction petition is saved under that name), and
    it is all there is to go on for a scan with no text read. A file the system drafted keeps
    the kind it was made as."""
    text = f"{Path(name).stem}\n{text}"
    kind = DRAFT_KINDS.get(petition_type, "petition") if petition_type else document_kind(text)
    return kind, legal_area(text)
