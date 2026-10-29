"""The detail section, generated only when the lawyer opens it, from the sources the short
answer already used. Citations come from the API, as for sub-question answers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from legal_api import llm
from legal_api.agent.atoms import Segment
from legal_api.config import get_settings
from legal_api.prompts import prompt

MAX_DOCUMENT_CHARS = 8000
MAX_DOCUMENTS = 12


async def detail_stream(question: str, short_answer: str, sources: list[tuple[str, str, str]],
                        usage: llm.Usage) -> AsyncIterator[str | list[Segment]]:
    """sources: (evidence key, citation, text). Yields text deltas, then the final segments."""
    sources = sources[:MAX_DOCUMENTS]
    documents = [{"type": "document",
                  "source": {"type": "text", "media_type": "text/plain",
                             "data": text[:MAX_DOCUMENT_CHARS]},
                  "title": citation, "citations": {"enabled": True}}
                 for _, citation, text in sources]
    request = f"Question: {question}\n\nShort answer already shown to the lawyer:\n{short_answer}"
    final = None
    async for item in llm.stream("main", usage, "detail", max_tokens=6000,
                                 system=prompt("detail"),
                                 output_config={"effort": get_settings().answer_effort},
                                 messages=[{"role": "user", "content": [
                                     *documents, {"type": "text", "text": request}]}]):
        if isinstance(item, str):
            yield item
        else:
            final = item
    segments = []
    for block in final.content if final else []:
        if block.type != "text":
            continue
        cites = block.citations or []
        keys = tuple(dict.fromkeys(sources[c.document_index][0] for c in cites
                                   if c.document_index < len(sources)))
        segments.append(Segment(block.text, keys, tuple(c.cited_text for c in cites)))
    yield segments
