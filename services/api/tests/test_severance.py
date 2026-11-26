import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from legal_api.calc.severance import compute, service_length


def test_length_of_service_counts_both_ends():
    s = service_length(date(2023, 3, 1), date(2026, 8, 31))
    assert (s.years, s.months, s.days) == (3, 6, 0)


def test_pay_above_the_ceiling_is_capped_and_notice_follows_length():
    r = compute(date(2023, 3, 1), date(2026, 8, 31), Decimal(100000))
    assert r.ceiling == Decimal("73729.87") and r.base == Decimal("73729.87")
    assert r.severance == Decimal("258054.55")          # 73,729.87 x 3.5 years
    assert r.notice_weeks == 8 and r.notice == Decimal("186666.67")   # 100,000/30 x 56


def test_under_one_year_gives_no_severance_and_unlisted_periods_are_flagged():
    r = compute(date(2026, 1, 1), date(2026, 5, 31), Decimal(40000))
    assert r.severance == 0 and "under_one_year" in r.warnings and r.notice_weeks == 2
    assert "ceiling_missing" in compute(date(2020, 1, 1), date(2021, 12, 31), Decimal(1)).warnings


def test_the_calculation_is_written_out_in_turkish_money_format():
    from legal_api.calc.severance_text import render
    text = render(compute(date(2023, 3, 1), date(2026, 8, 31), Decimal(100000)))
    assert "73.729,87 TL" in text and "258.054,55 TL" in text and "8 hafta" in text


def test_missing_ceiling_does_not_generate_a_purported_gross_or_net_amount():
    from legal_api.calc.severance_text import render
    from legal_api.locale import calculation_terms

    r = compute(date(2020, 1, 1), date(2027, 3, 1), Decimal(100000))
    text = render(r)
    words = calculation_terms()["severance"]
    assert words["ceiling_missing"].format(end="01.03.2027") in text
    assert words["severance"].split("{")[0] not in text
    assert words["stamp"].split("{")[0] not in text
    assert r.severance is None and r.stamp_duty is None


async def test_model_extracted_months_produce_sourced_calculation_without_fake_dates(monkeypatch):
    from legal_api.agent import pipeline
    from legal_api.agent.atoms import Segment
    from legal_api.agent.research import Research
    from legal_api.agent.write import Written
    from legal_api.calc import sources

    class Connection:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            pass

    class Clock:
        @staticmethod
        def now(zone):
            assert zone.key == "Europe/Istanbul"
            return SimpleNamespace(date=lambda: date(2026, 11, 26))

    question = "23 ay bir şirkette çalıştım. son brüt maaşım 200 bin sence ne kadar tazminat alırım"
    update = "İşveren beni çıkardı. Brüt ücrete düzenli ödemeler dahil."
    conversation = f"{question}\n{update}"
    monkeypatch.setattr(sources, "datetime", Clock)
    pool = SimpleNamespace(acquire=Connection, close=AsyncMock())
    monkeypatch.setattr(pipeline.asyncpg, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(pipeline, "indexed_laws", AsyncMock(return_value={}))
    monkeypatch.setattr(pipeline, "research", AsyncMock(return_value=Research()))
    monkeypatch.setattr(pipeline.SourceFinder, "article", AsyncMock(return_value=None))
    understanding = {
        "task": "consultation", "shape": "amount", "characterisation": "Kıdem tazminatı",
        "issues": [], "questions": [question], "clarify": [], "statute_hints": [],
        "case_law_query": "", "missing_facts": ["Sözleşme hangi gerekçeyle sona erdi?"],
        "severance": [{"start_date": "", "end_date": "", "service_months": 23,
                       "gross_monthly": 200000, "extras_monthly": 0,
                       "estimate_current_period": True}],
    }
    model = AsyncMock(return_value=SimpleNamespace(content=[
        SimpleNamespace(type="text", text=json.dumps(understanding))]))
    monkeypatch.setattr(pipeline.llm, "create", model)

    async def writer(message, u, evidence, _usage, *_args, **_kwargs):
        assert message == conversation and u.missing_facts == understanding["missing_facts"]
        calculation, ceiling = evidence
        assert calculation.evidence.kind == "calculation"
        assert "23 tam ay" in calculation.document and "26.11.2026 esas alındı" in calculation.document
        assert "141.315,58 TL" in calculation.document and "140.242,99 TL" in calculation.document
        assert "421.315,58 TL" in calculation.document
        assert "01.07.2026–31.12.2026" in ceiling.document
        assert "73.729,87 TL" in ceiling.document and "csgb.gov.tr" in ceiling.evidence.url
        yield Written([Segment("Koşullu tutar")], "Koşullu tutar", [])

    monkeypatch.setattr(pipeline, "write", writer)
    holder = {}
    async for _ in pipeline.answer_events(update, result=holder, search_text=conversation):
        pass
    answer = holder["result"]
    assert answer.question == update
    assert answer.text == "Koşullu tutar" and answer.understanding.shape == "amount"
    assert answer.usage.cost_usd == 0
    assert model.await_count == 1


def test_known_fesih_date_selects_its_period_with_months_only():
    from legal_api.calc.sources import severance_from_spec

    spec = {"service_months": 23, "gross_monthly": 200000, "end_date": "2024-06-30"}
    result, assumed = severance_from_spec(spec)
    assert not assumed and result.ceiling == Decimal("35058.58")
    result, assumed = severance_from_spec({**spec, "end_date": "2024-07-01"})
    assert not assumed and result.ceiling == Decimal("41828.42")
    assert severance_from_spec({**spec, "end_date": "invalid"}) is None
    assert severance_from_spec({**spec, "end_date": "", "estimate_current_period": False}) is None


def test_stated_twelve_months_uses_applicable_ceiling_without_inventing_a_start_date():
    from legal_api.calc.severance import compute_months
    from legal_api.calc.severance_text import render

    result = compute_months(12, date(2026, 11, 26), Decimal(100000))
    assert result.start is None
    assert result.severance == Decimal("73729.87")
    assert result.notice == Decimal("93333.33")
    shown = render(result, assumed_end=True)
    assert "12 tam ay" in shown and "26.11.2026" in shown
    assert "73.729,87 TL" in shown and "93.333,33 TL" in shown


def test_completed_calculation_keeps_evidence_when_the_writer_is_unavailable():
    from legal_api.agent.pipeline import _available_calculations
    from legal_api.agent.sources import Source
    from legal_api.grounding.evidence import EvidenceLedger

    ledger = EvidenceLedger()
    calculation = ledger.add_calculation(source_id="test", citation="Hesap", text="Hesap 1.200 TL.")
    fallback = _available_calculations([Source(calculation, "unverified writer draft")])
    assert fallback is not None
    assert f"Hesap 1.200 TL. [[{calculation.key}]]" in fallback.text
    assert "unverified" not in fallback.text
    assert _available_calculations([]) is None
