"""Case files ("dosya"): what a lawyer works in. A matter groups a client's chats, documents
and petitions, carries the facts every answer in it should know, and keeps its deadlines."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Matter(Base):
    __tablename__ = "matters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True)
    client: Mapped[str] = mapped_column(String(200))            # whose file it is
    subject: Mapped[str] = mapped_column(String(200), default="")   # what the case is about
    opponent: Mapped[str] = mapped_column(String(200), default="")
    court: Mapped[str] = mapped_column(String(200), default="")
    case_no: Mapped[str] = mapped_column(String(100), default="")   # esas no
    notes: Mapped[str] = mapped_column(Text, default="")        # facts every answer should know
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 index=True)


class MatterDeadline(Base):
    __tablename__ = "matter_deadlines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"),
                                                 index=True)
    label: Mapped[str] = mapped_column(String(200))
    due: Mapped[date] = mapped_column(Date, index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    # civil, criminal, enforcement, administrative or arbitration, when the lawyer chose one
    branch: Mapped[str | None] = mapped_column(String(20))
    # the answer whose calculation it came from, when added from one
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
