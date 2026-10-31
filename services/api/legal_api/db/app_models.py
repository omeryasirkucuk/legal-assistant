"""Users, chats, messages and the sources each assistant message cited."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LLMConnectionSettings(Base):
    """Shared provider connection edited by app administrators; credentials are encrypted."""

    __tablename__ = "llm_connection_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    base_url: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_main: Mapped[str] = mapped_column(String(200))
    model_draft: Mapped[str] = mapped_column(String(200))
    model_cheap: Mapped[str] = mapped_column(String(200))
    model_judge: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 onupdate=_now)

    __table_args__ = (CheckConstraint("id = 1", name="ck_llm_connection_settings_singleton"),)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    title: Mapped[str] = mapped_column(String(200))
    # the case file it belongs to (db/matter_models.py); None for a loose chat
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 index=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"),
                                               index=True)
    role: Mapped[str] = mapped_column(String(16))          # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)             # assistant: raw text with [[E#]]
    # assistant only: verification result, cost, timings, repaired/refused flags
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('turkish', content)", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_messages_tsv", "tsv", postgresql_using="gin"),)


class MessageEvidence(Base):
    """A source gathered while answering, kept so citations stay viewable later."""

    __tablename__ = "message_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(16))           # "E3"
    kind: Mapped[str] = mapped_column(String(16))          # "decision" | "article"
    citation: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("message_id", "key"),)


class LlmSpend(Base):
    """Model spend outside chat answers (a petition rewritten with a button, a sample petition
    read, a style learnt from edits), so the daily budget counts all of a lawyer's use."""

    __tablename__ = "llm_spend"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    purpose: Mapped[str] = mapped_column(String(40))       # "draft_adjust", "sample_read", ...
    cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 index=True)


# Chats point to matters: their table must be known wherever chats are.
from legal_api.db import matter_models  # noqa: F401
