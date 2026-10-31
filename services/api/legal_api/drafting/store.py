"""Reading and writing the lawyer's samples, style profile and drafts."""

from __future__ import annotations

import asyncio
import difflib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legal_api import llm
from legal_api.db.drafting_models import Draft, StyleProfile, StyleSample
from legal_api.drafting import memory
from legal_api.drafting.asking import record
from legal_api.drafting.brief import StyleBook
from legal_api.drafting.formats import choose, counted
from legal_api.drafting.profile import LENGTHS, REGISTERS, Preferences, Sample, targets
from legal_api.drafting.sample_profile import SampleProfile, analyze
from legal_api.drafting.style import WORDS_PER_PAGE, measure
from legal_api.drafting.types import petition_types
from legal_api.embeddings import embed_passages, embed_query

MAX_RULES = 20


async def profile_of(db: AsyncSession, user_id: uuid.UUID) -> StyleProfile:
    profile = await db.get(StyleProfile, user_id)
    if profile is None:
        profile = StyleProfile(user_id=user_id, rules=[], preferences={},
                               updated_at=datetime.now(UTC))
        db.add(profile)
        await db.flush()
    return profile


# Word overlap above which a new sample is taken for an edited copy of an existing one:
# measured on a lawyer's six divorce petitions, two different petitions shared at most 0.43,
# a copy with one of its paragraphs rewritten 0.87-0.90 and with half of it rewritten 0.58.
SAME_PETITION = 0.55


async def similar_sample(db: AsyncSession, user_id: uuid.UUID, text: str
                         ) -> tuple[StyleSample, float] | None:
    """The sample the text looks like an edited copy of, by word overlap (no model call;
    a few milliseconds for dozens of samples)."""
    words = text.split()
    best: tuple[StyleSample, float] | None = None
    for s in await samples_of(db, user_id):
        matcher = difflib.SequenceMatcher(None, words, s.text.split(), autojunk=False)
        if matcher.real_quick_ratio() < SAME_PETITION or matcher.quick_ratio() < SAME_PETITION:
            continue
        ratio = matcher.ratio()
        if ratio >= SAME_PETITION and (best is None or ratio > best[1]):
            best = (s, ratio)
    return best


async def has_sample_text(db: AsyncSession, user_id: uuid.UUID, text: str) -> bool:
    return await db.scalar(select(StyleSample.id).where(
        StyleSample.user_id == user_id, StyleSample.text == text).limit(1)) is not None


async def samples_of(db: AsyncSession, user_id: uuid.UUID) -> list[StyleSample]:
    return list((await db.scalars(select(StyleSample).where(StyleSample.user_id == user_id)
                                  .order_by(StyleSample.created_at.desc()))).all())


async def style_book(db: AsyncSession, user_id: uuid.UUID, case_text: str | None = None
                     ) -> StyleBook:
    """The lawyer's style; with `case_text`, the samples are scored by closeness in meaning to
    the case and the learnt preferences relevant to it are chosen (local model, no cost)."""
    profile = await db.get(StyleProfile, user_id)
    rows = await samples_of(db, user_id)
    scores: list[float | None] = [None] * len(rows)
    learnt: list[str] = []
    if case_text:
        query = await asyncio.to_thread(embed_query, case_text[:2000])
        scores = [sum(a * b for a, b in zip(query, s.embedding, strict=True))
                  if s.embedding is not None else None for s in rows]
        learnt = await memory.relevant(db, user_id, case_text, None)
    samples = []
    for s, score in zip(rows, scores, strict=True):
        read = SampleProfile.of(s.profile)
        samples.append(Sample(s.petition_type, s.style, s.text, s.description, score,
                              read.area, read.case_kind, read.matter))
    if profile is None:
        return StyleBook(samples, learnt=learnt)
    return StyleBook(samples, Preferences.of(profile.preferences), list(profile.rules), learnt,
                     dict(profile.preferences.get("asking", {})))


def _embedding_text(text: str, profile: SampleProfile) -> str:
    """What a sample is compared with a case by: the matter as the model put it, then the
    opening; the opening alone is mostly the court, the parties and their addresses."""
    return f"{profile.matter}\n{text[:1500]}" if profile.matter else text[:2000]


async def add_sample(db: AsyncSession, user_id: uuid.UUID, title: str, text: str,
                     petition_type: str | None,
                     profile: SampleProfile | None = None) -> StyleSample:
    profile = profile or SampleProfile()
    if petition_type not in petition_types():
        petition_type = None
    vector = (await asyncio.to_thread(embed_passages, [_embedding_text(text, profile)]))[0]
    sample = StyleSample(user_id=user_id, title=title[:200], text=text, embedding=vector,
                         petition_type=petition_type, style=measure(text).as_dict(),
                         profile=profile.as_dict(), created_at=datetime.now(UTC))
    db.add(sample)
    await db.commit()
    return sample


async def read_unread_samples(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Samples kept before the model read samples: read now, once."""
    rows = [s for s in await samples_of(db, user_id) if not s.profile]
    for s in rows:
        profile = await analyze(s.title, s.text, llm.Usage())
        s.profile = profile.as_dict()
        s.petition_type = s.petition_type or profile.petition_type
        s.embedding = (await asyncio.to_thread(embed_passages,
                                               [_embedding_text(s.text, profile)]))[0]
    if rows:
        await db.commit()


async def set_preferences(db: AsyncSession, user_id: uuid.UUID, prefs: Preferences) -> None:
    profile = await profile_of(db, user_id)
    profile.preferences = {**profile.preferences, **prefs.as_dict()}
    profile.updated_at = datetime.now(UTC)
    await db.commit()


async def record_reply(db: AsyncSession, user_id: uuid.UUID, skipped: bool) -> None:
    """The lawyer replied to a question turn: by answering, or by asking to write without."""
    profile = await profile_of(db, user_id)
    profile.preferences = {**profile.preferences,
                           "asking": record(profile.preferences.get("asking", {}), skipped)}
    profile.updated_at = datetime.now(UTC)
    await db.commit()


async def reset_learning(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Forget what was learnt (preferences moved by buttons and edits, the length and language
    chosen, formats counted, preferences from edits); the lawyer's own petitions and written
    wishes stay, as they are theirs to remove."""
    profile = await profile_of(db, user_id)
    profile.preferences = {}
    profile.updated_at = datetime.now(UTC)
    await db.commit()
    await memory.forget_all(db, user_id)


async def choose_style(db: AsyncSession, user_id: uuid.UUID, length: str | None,
                       register: str | None) -> Preferences:
    """The lawyer's own choice of length and language; earlier corrections start over from it."""
    prefs = Preferences(1.0, 0, length if length in LENGTHS else None,
                        register if register in REGISTERS else None)
    await set_preferences(db, user_id, prefs)
    return prefs


async def set_rules(db: AsyncSession, user_id: uuid.UUID, rules: list[str]) -> list[str]:
    profile = await profile_of(db, user_id)
    profile.rules = [r.strip() for r in rules if r.strip()][:MAX_RULES]
    profile.updated_at = datetime.now(UTC)
    await db.commit()
    return profile.rules


def summary(book: StyleBook) -> dict:
    """What has been learnt, per petition type, for the lawyer to read and correct."""
    per_type = {}
    for type_id, ptype in petition_types().items():
        t = targets(book.samples, book.preferences, type_id)
        per_type[type_id] = {"name": ptype.name, "words": t.words,
                             "words_per_sentence": t.words_per_sentence,
                             "register": t.register, "headings": t.headings,
                             "closing": t.closing, "learnt_from": t.learnt_from}
    overall = targets(book.samples, book.preferences, None)
    closings = [s.style.get("closing") for s in book.samples if s.style.get("closing")]
    return {"types": per_type, "rules": book.rules,
            "overall": {"pages": max(0.5, round(overall.words / WORDS_PER_PAGE * 2) / 2),
                        "register": overall.register,
                        "closing": max(set(closings), key=closings.count) if closings else None},
            "preferences": book.preferences.as_dict(), "samples": len(book.samples)}


async def file_format(db: AsyncSession, user_id: uuid.UUID, requested: str | None) -> str:
    """The format to deliver in; a format named in a message is counted, in any chat, so
    the lawyer's usual format is learnt."""
    profile = await profile_of(db, user_id)
    counts = profile.preferences.get("formats", {})
    new = counted(counts, requested)
    if new != counts:
        profile.preferences = {**profile.preferences, "formats": new}
        await db.commit()
    return choose(requested, new)


async def save_draft(db: AsyncSession, user_id: uuid.UUID, chat_id: uuid.UUID,
                     message_id: uuid.UUID, petition_type: str, title: str, text: str,
                     fmt: str) -> Draft:
    """A petition written in a chat, kept as an editable document delivered as a file.
    `first_text` stays as written, so a later save shows what the lawyer changed."""
    now = datetime.now(UTC)
    draft = Draft(user_id=user_id, chat_id=chat_id, petition_type=petition_type,
                  title=title[:200], text=text, created_at=now, updated_at=now,
                  meta={"message_id": str(message_id), "first_text": text, "format": fmt})
    db.add(draft)
    await db.commit()
    return draft
