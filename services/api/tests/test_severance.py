from datetime import date
from decimal import Decimal

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
    assert "ceiling_missing" in compute(date(2020, 1, 1), date(2024, 3, 1), Decimal(1)).warnings


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


def test_stated_twelve_months_uses_applicable_ceiling_without_inventing_a_start_date():
    from legal_api.calc.severance import compute_months
    from legal_api.calc.severance_text import render

    result = compute_months(12, date(2026, 11, 26), Decimal(100000))
    assert result.start is None
    assert result.severance == Decimal("73729.87")
    assert result.notice == Decimal("93333.33")
    shown = render(result, today_scenario=True)
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


def test_model_free_estimate_requires_a_clear_duration_pay_and_scenario():
    from legal_api.calc.severance import stated_dismissal_estimate

    question = ("bir hesaba ihtiyacım var. 12 aylık çalıştığım yerden atılsam kıdem ve ihbar "
                "alacağım nolur. maaşım 100 bin TL brüt")
    assert stated_dismissal_estimate(question) == {
        "start_date": "P12M", "end_date": "today", "gross_monthly": "100000", "extras_monthly": 0}
    for unclear in (question.replace("atılsam", "atıldım"), question + ", prim 10 bin TL",
                    question + ", fesih 01.12.2026", question.replace("12 aylık", "12 veya 13 aylık"),
                    question + ", 2 gün daha çalıştım"):
        assert stated_dismissal_estimate(unclear) is None
