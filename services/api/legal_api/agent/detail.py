"""The detail section, generated only when the lawyer opens it, from the sources the short
answer already used. Citations come from the API, as for sub-question answers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from legal_api import llm
from legal_api.agent.atoms import Segment, openai_segments_from
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
                  "title": f"{key} | {citation}", "citations": {"enabled": True}}
                 for key, citation, text in sources]
    request = f"Question: {question}\n\nShort answer already shown to the lawyer:\n{short_answer}"
    system = prompt("detail")
    if llm.uses_openai_compatible():
        keys = ", ".join(key for key, _, _ in sources)
        system += (f"\n\nKaynak kimlikleri: {keys}. Her maddi hukuki cümleden sonra ilgili "
                   "kaynağın birebir, kısa bir alıntısını <quote ref=\"E1\">alıntı</quote>[[E1]] "
                   "biçiminde ekle; E1'i gerçek kaynak kimliğiyle değiştir. Alıntı kaynakta "
                   "harfiyen bulunmalı. Kaynak kimliği ya da alıntı uydurma; desteklenemeyen "
                   "cümleyi yazma.")
    final = None
    async for item in llm.stream("main", usage, "detail", max_tokens=6000,
                                 system=system,
                                 output_config={"effort": get_settings().answer_effort},
                                 messages=[{"role": "user", "content": [
                                     *documents, {"type": "text", "text": request}]}]):
        if isinstance(item, str):
            yield item
        else:
            final = item
    segments = []
    if llm.uses_openai_compatible() and final:
        segments = openai_segments_from(final.content, sources)
        yield segments
        return
    for block in final.content if final else []:
        if block.type != "text":
            continue
        cites = block.citations or []
        keys = tuple(dict.fromkeys(sources[c.document_index][0] for c in cites
                                   if c.document_index < len(sources)))
        segments.append(Segment(block.text, keys, tuple(c.cited_text for c in cites)))
    yield segments
