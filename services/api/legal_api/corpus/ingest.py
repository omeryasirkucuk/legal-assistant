"""Load decisions from the public dataset's parquet files into the local corpus.

    uv run python -m legal_api.corpus.ingest FILE.parquet [--chamber NAME=LIMIT ...] [--limit N]

Without --chamber every row is loaded (up to --limit). Re-running skips decisions that are
already present. Embeddings are computed separately (legal_api.corpus.embed).
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

import asyncpg
import pyarrow.parquet as pq

from legal_api.config import get_settings
from legal_api.corpus.chunking import chunk_text
from legal_api.corpus.records import DecisionRecord, from_dataset_row

COLUMNS = ["id", "source", "document_id", "court", "esas_no", "karar_no", "karar_tarihi",
           "text", "raw_sha256"]


def asyncpg_dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def select_rows(path: Path, chamber_limits: dict[str, int] | None, limit: int | None):
    table = pq.read_table(path, columns=COLUMNS)
    taken: Counter[str] = Counter()
    total = 0
    for batch in table.to_batches(max_chunksize=2048):
        for row in batch.to_pylist():
            if limit is not None and total >= limit:
                return
            if not row.get("text"):
                continue
            court = (row.get("court") or "").strip()
            if chamber_limits is not None:
                cap = chamber_limits.get(court)
                if cap is None or taken[court] >= cap:
                    continue
            taken[court] += 1
            total += 1
            yield row


async def insert(conn: asyncpg.Connection, records: list[DecisionRecord]) -> int:
    existing = {r["id"] for r in await conn.fetch(
        "SELECT id FROM corpus_decisions WHERE id = ANY($1::text[])", [r.id for r in records])}
    fresh = [r for r in records if r.id not in existing]
    if not fresh:
        return 0
    async with conn.transaction():
        await conn.copy_records_to_table(
            "corpus_decisions",
            columns=["id", "source", "chamber", "case_no", "decision_no", "decision_date", "url",
                     "text", "raw_sha256"],
            records=[(r.id, r.source, r.chamber, r.case_no, r.decision_no, r.decision_date, r.url,
                      r.text, r.raw_sha256) for r in fresh],
        )
        await conn.copy_records_to_table(
            "corpus_chunks",
            columns=["decision_id", "ordinal", "start_char", "text"],
            records=[(r.id, c.ordinal, c.start, c.text) for r in fresh for c in chunk_text(r.text)],
        )
    return len(fresh)


async def run(path: Path, chamber_limits: dict[str, int] | None, limit: int | None) -> None:
    conn = await asyncpg.connect(asyncpg_dsn())
    try:
        batch: list[DecisionRecord] = []
        loaded = 0
        for row in select_rows(path, chamber_limits, limit):
            batch.append(from_dataset_row(row))
            if len(batch) == 500:
                loaded += await insert(conn, batch)
                batch.clear()
        if batch:
            loaded += await insert(conn, batch)
        print(f"{path.name}: loaded {loaded} new decisions")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--chamber", action="append", default=[], metavar="NAME=LIMIT")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    limits = {name: int(cap) for name, cap in (c.rsplit("=", 1) for c in args.chamber)} or None
    asyncio.run(run(args.file, limits, args.limit))


if __name__ == "__main__":
    main()
