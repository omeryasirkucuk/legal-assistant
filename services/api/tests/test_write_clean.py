import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from legal_api import llm
from legal_api.agent import write
from legal_api.agent.atoms import Segment
from legal_api.agent.sources import Source
from legal_api.agent.understand import Understanding
from legal_api.agent.write import clean
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.grounding.numbers import numbers_in


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
        Segment("Bu durumda başvuru süresi 14 gündür.\n\n", (evidence.key,), (text,)),
        Segment("Bütün başvurularda bu süre aynıdır.\n\n", (evidence.key,)),
        Segment("Diğer kaynak farklı bir olayı anlatır.", (other.key,)),
    ]

    async def verdict(_client, state, questions, _usage, _purpose):
        if len(questions) == 2:
            assert "Other" not in state["sources"]
            assert state["case_facts"] == "Karar dün tebliğ edildi."
            assert state["claims"]["claim_0"]["verified_quotations"] == [text]
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
                              "Karar dün tebliğ edildi.", llm.Usage())

    assert judge.await_count == 2
    assert len(flags) == 1
    assert flags[0]["reason"] == "support_low"
    assert flags[0]["sentence"] == segments[2].text.strip()


async def test_verifier_distinguishes_amounts_and_citation_fragments(monkeypatch):
    @asynccontextmanager
    async def client():
        yield object()

    ledger = EvidenceLedger()
    calculation = "Kıdem tazminatı 141.315,58 TL, ihbar tazminatı 280.000,00 TL."
    calc = ledger.add_calculation(source_id="calc", citation="Kıdem ve ihbar tazminatı hesabı",
                                  text=calculation)
    legal = ledger.add_calculation(source_id="law", citation="1475 sayılı İş Kanunu, m. 14",
                                   text="Hesap yöntemini düzenleyen madde.")
    segments = [
        Segment("Her iki tazminata hak kazanılırsa kıdem tutarı 141.315,58 TL olur.\n\n",
                (calc.key,)),
        Segment("| Dayanak | 1475 sayılı İş Kanunu m. ", (legal.key,)),
        Segment("14 ve Kıdem ve ihbar tazminatı hesabı", (legal.key, calc.key)),
        Segment(" |\n\n"),
        Segment("İhbar tazminatı 280.000,58 TL olur.", (calc.key,)),
    ]

    async def verdict(_client, state, questions, _usage, _purpose):
        assert list(questions) == ["claim_0"]
        assert state["claims"]["claim_0"]["text"].startswith("Her iki tazminata")
        return {"claim_0": 0.96}

    judge = AsyncMock(side_effect=verdict)
    monkeypatch.setattr(write.decisions, "enabled", lambda: True)
    monkeypatch.setattr(write.decisions, "client", client)
    monkeypatch.setattr(write.decisions, "yes_probabilities", judge)
    sources = [Source(calc, calculation), Source(legal, legal.text)]
    flags = await write.check(segments, sources, "", llm.Usage())

    assert judge.await_count == 1
    assert [flag["sentence"] for flag in flags] == [segments[-1].text]


def test_recurring_period_still_counts_as_a_quantity():
    assert numbers_in("Her iki ayda bir bildirim yapılır.") == {2}


async def test_timed_out_citation_retry_preserves_first_answer(monkeypatch):
    attempts = 0

    async def stream(*args, **kwargs):
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
        "Soru", Understanding(task="lookup"), [Source(evidence, "Kural")], llm.Usage())]
    assert attempts == 2
    assert items[-1].text == "İlk yanıt"
    assert any(flag.get("reason") == "citation_missing" for flag in items[-1].flagged)
