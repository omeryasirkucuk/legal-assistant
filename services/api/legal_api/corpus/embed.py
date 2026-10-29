"""Fill in missing chunk embeddings.

    uv run python -m legal_api.corpus.embed [--batch 512]

Safe to stop and resume: only chunks with a NULL embedding are processed.
"""

from __future__ import annotations

import argparse
import asyncio
import time

import asyncpg
from pgvector.asyncpg import register_vector

from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.embeddings import embed_passages


async def run(batch_size: int) -> None:
    conn = await asyncpg.connect(asyncpg_dsn())
    await register_vector(conn)
    try:
        remaining = await conn.fetchval("SELECT count(*) FROM corpus_chunks WHERE embedding IS NULL")
        done, started = 0, time.monotonic()
        while True:
            rows = await conn.fetch(
                "SELECT id, text FROM corpus_chunks WHERE embedding IS NULL ORDER BY id LIMIT $1",
                batch_size)
            if not rows:
                break
            vectors = embed_passages([r["text"] for r in rows])
            await conn.executemany(
                "UPDATE corpus_chunks SET embedding = $2 WHERE id = $1",
                [(r["id"], v) for r, v in zip(rows, vectors, strict=True)])
            done += len(rows)
            rate = done / (time.monotonic() - started)
            print(f"{done}/{remaining} chunks, {rate:.0f}/s, "
                  f"~{(remaining - done) / rate / 60:.1f} min left", flush=True)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=512)
    asyncio.run(run(parser.parse_args().batch))


if __name__ == "__main__":
    main()
