"""Encrypt existing attachments and generated files with the API offline."""

import asyncio

from legal_api.db.session import get_sessionmaker
from legal_api.files.store import encrypt_existing


async def main() -> None:
    async with get_sessionmaker()() as session:
        converted = await encrypt_existing(session)
    print(f"Encrypted {converted} existing files")


if __name__ == "__main__":
    asyncio.run(main())
