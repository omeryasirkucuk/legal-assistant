from datetime import date
from decimal import Decimal

from legal_api.calc.court_costs import appeal, chain, fees
from legal_api.calc.court_costs_sources import render
from legal_api.locale import court_costs

DATA = court_costs()
W = DATA["words"]


def test_every_years_limit_follows_from_the_revaluation_rates():
    years = sorted(int(y) for y in DATA["revaluation"])
    rates = [Decimal(DATA["revaluation"][str(y)]) for y in years]
    for kind in ("istinaf", "temyiz", "hearing"):
        table = {int(y): v for y, v in DATA["limits"][kind].items()}
        assert chain(table[DATA["first_year"]], rates, 2025, DATA["first_year"]) == table


def test_the_limit_of_the_filing_year_decides_the_appeal():
    filed_2023 = appeal(Decimal(30000), date(2023, 5, 1))
    assert filed_2023.istinaf and not filed_2023.temyiz          # 2023 limit 17,830
    assert not appeal(Decimal(45000), date(2026, 3, 1)).istinaf   # 2026 limit 50,000
    assert appeal(Decimal(700000), date(2026, 3, 1)).temyiz
    assert not appeal(Decimal(682000), date(2026, 3, 1)).temyiz   # the limit itself is final
    assert appeal(Decimal(1000), date(2015, 1, 1)) is None


def test_proportional_fee_and_the_quarter_due_in_advance():
    f = fees(Decimal(100000), "asliye", "proportional")
    assert f.proportional == Decimal("6831.00") and f.advance == Decimal("1707.75")
    assert f.application == Decimal("732.00") and f.fixed is None
    small = fees(Decimal(1000), "sulh", "proportional")
    assert small.proportional == Decimal("732.00") and small.application == Decimal("335.20")
    harm = fees(Decimal(100000), "asliye", "proportional", bodily_harm=True)
    assert harm.advance == Decimal("341.55")


def test_the_calculation_text_names_the_filing_year_or_warns_without_it():
    text = render(Decimal(100000), "asliye", "proportional", False, date(2023, 5, 1), date(2026, 10, 31))
    assert W["filing_total"].format(amount="2.439,75") in text
    assert W["appeal_year"].format(year=2023) in text
    guessed = render(Decimal(100000), "asliye", "unknown", False, None, date(2026, 10, 31))
    assert W["year_unknown"].format(year=2026) in guessed and W["unknown_measure"] in guessed
