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
