"""Text normalisation used when comparing model output with source text.

Turkish casing differs from the default Unicode mapping (I <-> i-dotless, I-dotted <-> i), so
plain `str.lower()` would make a correct quote look wrong.
"""

from __future__ import annotations

import re
import unicodedata

_TR_UPPER = str.maketrans({"I": "\u0131", "\u0130": "i"})
_TR_LOWER = str.maketrans({"i": "\u0130", "\u0131": "I"})
_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", " ": " ",
})


def tr_fold(text: str) -> str:
    """Casefold with Turkish rules, unify quotes/dashes, collapse whitespace."""
    text = unicodedata.normalize("NFC", text).translate(_PUNCT).translate(_TR_UPPER).lower()
    return re.sub(r"\s+", " ", text).strip()


def contains_quote(source: str, quote: str) -> bool:
    """True if `quote` appears verbatim in `source` after normalisation.

    Ellipses inside a quote ("...") mark omitted text: each fragment must appear, in order.
    """
    haystack = tr_fold(source)
    fragments = [tr_fold(f) for f in re.split(r"\.{3}|…|\[\.\.\.\]", quote)]
    fragments = [f.strip(" \"'") for f in fragments if f.strip(" \"'")]
    if not fragments:
        return False
    cursor = 0
    for fragment in fragments:
        found = haystack.find(fragment, cursor)
        if found < 0:
            return False
        cursor = found + len(fragment)
    return True


def tr_lower(text: str) -> str:
    return text.translate(_TR_UPPER).lower()


def tr_title(text: str, keep_lower: frozenset[str] = frozenset()) -> str:
    """Title-case with Turkish dotted/dotless i rules; words in `keep_lower` stay lowercase."""
    words = tr_lower(text).split()
    out = []
    for i, word in enumerate(words):
        if i and word in keep_lower:
            out.append(word)
        else:
            out.append(word[:1].translate(_TR_LOWER).upper() + word[1:])
    return " ".join(out)
