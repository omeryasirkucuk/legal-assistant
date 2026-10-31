from datetime import date
from decimal import Decimal

from legal_api.calc.interest import compute


def test_statutory_interest_is_split_where_the_rate_changed():
    r = compute(Decimal(100000), date(2026, 6, 30), date(2026, 8, 30), "statutory")
    assert [(s.rate, s.days) for s in r.stretches] == [(Decimal(24), 30), (Decimal(31), 31)]
    # 100,000 x 24% x 30/365 + 100,000 x 31% x 31/365
    assert r.total == Decimal("1972.60") + Decimal("2632.88")


def test_advance_interest_follows_the_central_bank_table():
    r = compute(Decimal(50000), date(2025, 12, 1), date(2025, 12, 31), "advance")
    assert [(s.rate, s.days) for s in r.stretches] == [(Decimal("42.25"), 18), (Decimal("39.75"), 12)]


def test_days_outside_the_tables_are_flagged():
    assert "before_rates" in compute(Decimal(1), date(2017, 1, 1), date(2019, 1, 1), "advance").warnings
    assert "after_known" in compute(Decimal(1), date(2026, 1, 1), date(2027, 6, 1), "statutory").warnings


def test_the_calculation_is_written_out_with_both_kinds_when_unclear():
    from legal_api.calc.interest_text import render
    text = render([compute(Decimal(100000), date(2026, 6, 30), date(2026, 8, 30), k)
                   for k in ("statutory", "advance")])
    assert "%24:" in text and "%31:" in text and "%39,75:" in text
    assert "4.605,48 TL" in text
