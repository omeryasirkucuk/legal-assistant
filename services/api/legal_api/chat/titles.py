"""A short chat title written from the first question, instead of its first characters."""

from __future__ import annotations

import json

from legal_api import llm
from legal_api.config import get_settings
from legal_api.prompts import prompt

MAX_TITLE_CHARS = 80

_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


async def generate_title(question: str, usage: llm.Usage) -> str | None:
    response = await llm.create(
        "cheap", usage, "title", max_tokens=1000, system=prompt("title"),
        messages=[{"role": "user", "content": question[:2000]}],
        output_config={"effort": get_settings().answer_effort,
                       "format": {"type": "json_schema", "schema": _SCHEMA}})
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return None
    title = " ".join(json.loads(text)["title"].split()).strip(" .\"'")
    return title[:MAX_TITLE_CHARS] or None


async def backfill() -> None:
    """Title chats that still carry the provisional title cut from their first question."""
    from sqlalchemy import select

    from legal_api.chat.service import title_from
    from legal_api.db.app_models import Chat, Message
    from legal_api.db.session import get_sessionmaker

    usage = llm.Usage()
    async with get_sessionmaker()() as db:
        for chat in (await db.scalars(select(Chat))).all():
            first = await db.scalar(select(Message.content).where(
                Message.chat_id == chat.id, Message.role == "user")
                .order_by(Message.created_at).limit(1))
            if first and chat.title == title_from(first):
                chat.title = await generate_title(first, usage) or chat.title
        await db.commit()
    print(f"titles written, ${usage.cost_usd:.4f}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(backfill())
