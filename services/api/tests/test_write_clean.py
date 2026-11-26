from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from legal_api import llm
from legal_api.agent import write
from legal_api.agent.atoms import Segment
from legal_api.agent.sources import Source
from legal_api.agent.write import clean
from legal_api.grounding.evidence import EvidenceLedger


def test_raw_document_keys_cannot_create_citations():
    text = "The closest are E10 and E12 (case E. 2016/8646) [[E3]]."
    assert clean(text) == "The closest are E10 and E12 (case E. 2016/8646)."


def test_invisible_characters_are_removed():
    assert clean("a\u200bb") == "ab"


async def test_support_check_batches_claims_on_the_same_sources(monkeypatch):
    @asynccontextmanager
    async def client():
        yield object()

    ledger = EvidenceLedger()
    text = "İlgili başvuru süresi 14 gündür."
    evidence = ledger.add_calculation(source_id="a", citation="Source", text=text)
    other = ledger.add_calculation(source_id="b", citation="Other", text=text)
    segments = [
        Segment("Yalnızca ilk paragrafın başlangıcı. "),
        Segment("Bu durumda başvuru süresi 14 gündür.\n\n", (evidence.key,)),
        Segment("Bütün başvurularda bu süre aynıdır.\n\n", (evidence.key,)),
        Segment("Diğer kaynak farklı bir olayı anlatır.", (other.key,)),
    ]

    async def verdict(_client, state, questions, _usage, _purpose):
        if len(questions) == 2:
            assert "Other" not in state["sources"]
            context = state["claims"]["claim_0"]["context"]
            assert "ilk paragrafın başlangıcı" in context
            assert "Bütün başvurularda" not in context
            return {"claim_0": 0.95, "claim_1": 0.3}
        assert "Other" in state["sources"]
        return {"claim_0": None}

    judge = AsyncMock(side_effect=verdict)
    monkeypatch.setattr(write.decisions, "enabled", lambda: True)
    monkeypatch.setattr(write.decisions, "client", client)
    monkeypatch.setattr(write.decisions, "yes_probabilities", judge)
    flags = await write.check(segments, [Source(evidence, text), Source(other, text)],
                              "", llm.Usage())

    assert judge.await_count == 2
    assert len(flags) == 1
    assert flags[0]["reason"] == "support_low"
    assert flags[0]["sentence"] == segments[2].text.strip()
