"""The lawyer's own petitions (style samples), their style profile, and drafts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base
from legal_api.db.corpus_models import EMBEDDING_DIM


def _now() -> datetime:
    return datetime.now(UTC)


class StyleSample(Base):
    """A petition the lawyer wrote: uploaded, or a draft they saved after editing."""
    __tablename__ = "style_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    petition_type: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    style: Mapped[dict] = mapped_column(JSONB, default=dict)       # drafting.style.Style
    description: Mapped[str] = mapped_column(Text, default="")     # the voice, in words
    origin: Mapped[str] = mapped_column(String(16), default="upload")  # upload | saved_draft
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # what the sample is, as the model read it (drafting/sample_profile.py); {} until read
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StyleProfile(Base):
    """What was learnt about the lawyer's style beyond the samples themselves."""
    __tablename__ = "style_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    rules: Mapped[list] = mapped_column(JSONB, default=list)        # stated by the lawyer
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)  # moved by feedback
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chats.id", ondelete="SET NULL"), index=True)
    petition_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)              # as written, with [[E#]] markers
    # sources (evidence copies), checklist, cost, and the text the system wrote first
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StyleMemory(Base):
    """A preference learnt about how the lawyer writes ("asks for occupation compensation in
    eviction suits"), kept as a sentence with its meaning vector so only the ones relevant to
    a case are given to the writer."""
    __tablename__ = "style_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    text: Mapped[str] = mapped_column(Text)
    petition_type: Mapped[str | None] = mapped_column(String(40))
    # Separate edits that showed it; used for drafting only from MIN_SEEN on.
    seen: Mapped[int] = mapped_column(default=1)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
