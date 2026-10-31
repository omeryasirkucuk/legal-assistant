"""Preferences learnt from the lawyer's edits, kept small and chosen by meaning.

When the lawyer saves an edited draft, the cheap model compares the petition as written and
as saved and states at most three general writing preferences it shows ("puts procedural
objections before the merits"). This runs after the save, in the background, so it adds no
wait. To keep the learning from drifting:
- only style and structure are kept: a sentence with a number (an amount, a date, an article)
  is case material, not a preference, and is dropped, as is anything the model marks as
  specific to this case;
- a preference is used for drafting only after separate edits have shown it MIN_SEEN times;
  the same preference found again (by meaning) is counted, not stored twice;
- at most MAX_MEMORIES are kept; the least confirmed, oldest go first;
- the writer is told these never override the legal rules, and the lawyer can see, delete
  or reset them.
When drafting, only the TOP_K preferences closest in meaning to the case are given, so the
prompt does not grow with the lawyer's history.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api import llm
from legal_api.db.drafting_models import StyleMemory
from legal_api.db.session import get_sessionmaker
from legal_api.drafting.style import petition_part
from legal_api.embeddings import embed_passages, embed_query
from legal_api.prompts import prompt
from legal_api.spend import record_spend

logger = logging.getLogger(__name__)

MIN_SEEN = 2
SAME = 0.92               # cosine similarity at which two preferences say the same thing
MAX_MEMORIES = 60
TOP_K = 6
MAX_PER_EDIT = 3
UNCHANGED = 0.98          # edits this similar to the draft teach nothing; no model call
EDIT_CHARS = 12000
_SCHEMA = {
    "type": "object",
    "properties": {"preferences": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "general": {"type": "boolean"}},
        "required": ["text", "general"], "additionalProperties": False}}},
    "required": ["preferences"],
    "additionalProperties": False,
}


def acceptable(text: str) -> bool:
    text = text.strip()
    return 15 <= len(text) <= 200 and not re.search(r"\d", text)


async def _extract(before: str, after: str, usage: llm.Usage) -> list[str]:
    response = await llm.create(
        "cheap", usage, "style_memory", max_tokens=1500, system=prompt("style_extract"),
        messages=[{"role": "user", "content": (
            f"<as_written>\n{before[:EDIT_CHARS]}\n</as_written>\n"
            f"<as_saved>\n{after[:EDIT_CHARS]}\n</as_saved>")}],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), "")
    found = json.loads(text)["preferences"] if text else []
    return [p["text"].strip() for p in found if p["general"] and acceptable(p["text"])][
        :MAX_PER_EDIT]


async def remember(db: AsyncSession, user_id: uuid.UUID, texts: list[str],
                   petition_type: str | None) -> None:
    """Count each preference: a known one (same meaning) is seen once more, a new one added."""
    if not texts:
        return
    vectors = await asyncio.to_thread(embed_passages, texts)
    now = datetime.now(UTC)
    for text, vector in zip(texts, vectors, strict=True):
        closest = (await db.execute(
            select(StyleMemory, StyleMemory.embedding.cosine_distance(vector).label("d"))
            .where(StyleMemory.user_id == user_id).order_by("d").limit(1))).first()
        if closest is not None and 1 - closest.d >= SAME:
            closest.StyleMemory.seen += 1
            closest.StyleMemory.updated_at = now
        else:
            db.add(StyleMemory(user_id=user_id, text=text, petition_type=petition_type,
                               seen=1, embedding=vector, created_at=now, updated_at=now))
    await db.flush()
    extra = (await db.scalars(select(StyleMemory.id).where(StyleMemory.user_id == user_id)
                              .order_by(StyleMemory.seen.desc(), StyleMemory.updated_at.desc())
                              .offset(MAX_MEMORIES))).all()
    if extra:
        await db.execute(delete(StyleMemory).where(StyleMemory.id.in_(extra)))
    await db.commit()


async def learn_from_edit(user_id: uuid.UUID, drafted: str, saved: str,
                          petition_type: str | None) -> None:
    """Run after a draft is saved (in the background); errors are logged, never raised."""
    before, after = petition_part(drafted), petition_part(saved)
    if difflib.SequenceMatcher(None, before, after).quick_ratio() >= UNCHANGED:
        return
    try:
        usage = llm.Usage()
        texts = await _extract(before, after, usage)
        async with get_sessionmaker()() as db:
            await record_spend(db, user_id, "style_learning", usage)
            await remember(db, user_id, texts, petition_type)
    except Exception:
        logger.exception("learning from an edit failed")


async def relevant(db: AsyncSession, user_id: uuid.UUID, case_text: str,
                   petition_type: str | None) -> list[str]:
    """The confirmed preferences closest in meaning to the case."""
    query = await asyncio.to_thread(embed_query, case_text[:2000])
    rows = (await db.scalars(
        select(StyleMemory).where(
            StyleMemory.user_id == user_id, StyleMemory.seen >= MIN_SEEN,
            (StyleMemory.petition_type.is_(None)) | (StyleMemory.petition_type == petition_type)
            if petition_type else StyleMemory.id.is_not(None))
        .order_by(StyleMemory.embedding.cosine_distance(query)).limit(TOP_K))).all()
    return [m.text for m in rows]


async def forget_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(StyleMemory).where(StyleMemory.user_id == user_id))
    await db.commit()
