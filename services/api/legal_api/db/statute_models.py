"""Local copy of core legislation, one row per article, for search and fast lookup."""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base
from legal_api.db.corpus_models import EMBEDDING_DIM


class StatuteArticle(Base):
    __tablename__ = "statute_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law_number: Mapped[str] = mapped_column(String(16), index=True)   # "2004"
    law_title: Mapped[str] = mapped_column(Text)
    statute_id: Mapped[str] = mapped_column(String(32))               # Bedesten legislation id
    kind: Mapped[str] = mapped_column(String(16))                     # main | additional | temporary
    label: Mapped[str] = mapped_column(String(32))                    # "269/a", "ek 1"
    position: Mapped[int] = mapped_column(Integer)                    # order within the law
    heading: Mapped[str] = mapped_column(Text, default="")            # marginal title
    # Titles of the parts and chapters the article sits in, outermost first, joined by " > "
    # ("Lease contract > Crop lease"): the same marginal title means different things in
    # different chapters, so the chapter decides which regime an article belongs to.
    section: Mapped[str] = mapped_column(Text, default="", server_default="")
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('turkish', heading || ' ' || text)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        UniqueConstraint("law_number", "kind", "label"),
        Index("ix_statute_articles_tsv", "tsv", postgresql_using="gin"),
    )
