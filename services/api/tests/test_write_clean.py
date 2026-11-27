import asyncio
from datetime import date
from types import SimpleNamespace

from legal_api import llm
from legal_api.agent import write
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.agent.write import clean
from legal_api.grounding.evidence import EvidenceLedger


def test_raw_document_keys_cannot_create_citations():
    text = "The closest are E10 and E12 (case E. 2016/8646) [[E3]]."
    assert clean(text) == "The closest are E10 and E12 (case E. 2016/8646)."


def test_invisible_characters_are_removed():
    assert clean("a\u200bb") == "ab"


async def test_timed_out_citation_retry_preserves_first_answer(monkeypatch):
    attempts = 0

    async def stream(*args, **kwargs):
        assert "<yesterday>2026-11-26</yesterday>" in kwargs["system"]
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            await asyncio.Future()
        yield "İlk yanıt"
        yield SimpleNamespace(content=[SimpleNamespace(type="text", text="İlk yanıt", citations=None)],
                              stop_reason="stop")

    monkeypatch.setattr(llm, "stream", stream)
    monkeypatch.setattr(llm, "openai_for", lambda _role: False)
    monkeypatch.setattr(write, "CITATION_RETRY_S", 0)
    evidence = EvidenceLedger().add_calculation(source_id="a", citation="Source", text="Kural")
    items = [item async for item in write.write(
        "Soru", Understanding(task="lookup"), [Source(evidence, "Kural")], llm.Usage(),
        today=date(2026, 11, 27))]
    assert attempts == 2
    assert items[-1].text == "İlk yanıt"
    assert any(flag.get("reason") == "citation_missing" for flag in items[-1].flagged)
