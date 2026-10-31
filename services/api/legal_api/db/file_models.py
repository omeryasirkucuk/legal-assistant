"""Files a user keeps: attachments they added and files the system made for them."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class StoredFile(Base):
    __tablename__ = "stored_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chats.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), index=True)
    # added straight to a case file's documents (files from its chats are found by chat)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    # the lawyer's own folder in My files (none: the top level)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_folders.id", ondelete="SET NULL"), index=True)
    origin: Mapped[str] = mapped_column(String(16))         # "upload" | "generated"
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)                 # relative to the storage dir
    text: Mapped[str] = mapped_column(Text, default="")     # extracted text, for answers
    # what the file is, for filtering (files/labels.py); None until labelled
    kind: Mapped[str | None] = mapped_column(String(32))    # petition, decision, contract, ...
    area: Mapped[str | None] = mapped_column(String(32))    # labour, tenancy, family, ...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FileFolder(Base):
    """A folder the lawyer made in My files; folders can hold folders."""
    __tablename__ = "file_folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_folders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
