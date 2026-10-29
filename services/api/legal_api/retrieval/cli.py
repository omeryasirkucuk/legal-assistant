"""Try local hybrid search from the terminal.

    uv run python -m legal_api.retrieval.cli "kiracinin ihtiyac nedeniyle tahliyesi" [-n 5]
"""

from __future__ import annotations

import argparse
import asyncio

import asyncpg
from pgvector.asyncpg import register_vector

from legal_api.corpus.ingest import asyncpg_dsn
from legal_api.retrieval.hybrid import search


async def run(query: str, limit: int) -> None:
    conn = await asyncpg.connect(asyncpg_dsn())
    await register_vector(conn)
    try:
        for i, hit in enumerate(await search(conn, query, limit), 1):
            print(f"{i}. {hit.chamber}, E. {hit.case_no} K. {hit.decision_no}, "
                  f"T. {hit.decision_date}  [{hit.score:.4f}]")
            print(f"   {hit.url}")
            print(f"   {' '.join(hit.passage.split())[:300]}\n")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("-n", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.query, args.n))


if __name__ == "__main__":
    main()
