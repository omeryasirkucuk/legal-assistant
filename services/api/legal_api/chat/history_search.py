"""Search over the user's chats as they type: partial words count.

A lawyer types the start of a word ("ağırlaş") and expects the chat that says
"ağırlaştırılmış". Full-text search alone only matches whole stemmed words, so every typed
term is matched three ways: as a word prefix in the full-text index, as text inside a
message (folded with Turkish casing rules, so it also finds the middle of a word), and in the
chat title. A chat matches when every term matches somewhere in it.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import Text, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api.db.app_models import Chat, Message
from legal_api.grounding.normalize import tr_fold

MAX_RESULTS = 30
MAX_TERMS = 6
SNIPPET_CHARS = 70
# Citation markers and section tags are not text the lawyer sees.
_MARKUP = re.compile(r"\[\[E\d+\]\]|</?(?:short|detail|quote[^>]*)>")
_BULLET = re.compile(r"(?m)^\s*- ")


def _terms(q: str) -> list[str]:
    words = [w for w in re.findall(r"\w+", tr_fold(q)) if len(w) >= 2]
    return list(dict.fromkeys(words))[:MAX_TERMS]


def _folded(column):
    """Turkish casefold in SQL: dotted capital I to i and plain I to dotless i, then lower."""
    return func.lower(func.translate(column, "İI", "iı"))


def _term_matches(term: str):
    pattern = f"%{term}%"
    prefix = func.to_tsquery("turkish", literal(f"{term}:*", Text))
    return or_(Message.tsv.op("@@")(prefix),
               _folded(Message.content).like(pattern),
               _folded(Chat.title).like(pattern))


def snippet(content: str, terms: list[str]) -> str:
    """A short window around the first match, matches wrapped in << >>."""
    text = " ".join(_BULLET.sub(" ", _MARKUP.sub(" ", content)).split())
    folded = tr_fold(text)
    hits = [(folded.find(t), t) for t in terms if folded.find(t) >= 0]
    if not hits:
        return text[:2 * SNIPPET_CHARS]
    first = min(i for i, _ in hits)
    start = max(0, first - SNIPPET_CHARS)
    end = min(len(text), first + SNIPPET_CHARS)
    window = text[start:end]
    folded_window = folded[start:end]
    spans = sorted({(m.start(), m.end()) for _, t in hits
                    for m in re.finditer(re.escape(t), folded_window)})
    out, cursor = [], 0
    for a, b in spans:
        if a < cursor:
            continue
        out += [window[cursor:a], "<<", window[a:b], ">>"]
        cursor = b
    out.append(window[cursor:])
    return ("…" if start else "") + "".join(out) + ("…" if end < len(text) else "")


async def search_chats(db: AsyncSession, user_id: uuid.UUID, q: str) -> list[dict]:
    terms = _terms(q)
    if not terms:
        return []
    rows = await db.execute(
        select(Chat.id, Chat.title, Message.content)
        .join(Message, Message.chat_id == Chat.id)
        .where(Chat.user_id == user_id, and_(*(_term_matches(t) for t in terms)))
        .order_by(Chat.updated_at.desc(), Message.created_at.desc())
        .limit(MAX_RESULTS * 4))
    seen: dict[str, dict] = {}
    for chat_id, title, content in rows:
        key = str(chat_id)
        if key not in seen and len(seen) < MAX_RESULTS:
            seen[key] = {"chat_id": key, "title": title, "snippet": snippet(content, terms)}
    return list(seen.values())
