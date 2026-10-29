"""Local copy of public court decisions, chunked for hybrid (full-text + vector) search."""

from __future__ import annotations

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from legal_api.db.base import Base

EMBEDDING_DIM = 384


class CorpusDecision(Base):
    __tablename__ = "corpus_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "<source>:<document_id>"
    source: Mapped[str] = mapped_column(String(16), index=True)
    chamber: Mapped[str] = mapped_column(String)
    case_no: Mapped[str | None] = mapped_column(String)
    decision_no: Mapped[str | None] = mapped_column(String)
    decision_date: Mapped[date | None] = mapped_column(Date, index=True)
    url: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    raw_sha256: Mapped[str] = mapped_column(String(64))


class CorpusChunk(Base):
    __tablename__ = "corpus_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_decisions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    start_char: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('turkish', text)", persisted=True)
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_corpus_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_corpus_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
