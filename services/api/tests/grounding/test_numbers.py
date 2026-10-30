import json
from pathlib import Path

from legal_api.grounding.numbers import digits_for_quantities, numbers_in, unsupported_numbers

TEXT = json.loads((Path(__file__).parents[1] / "fixtures" / "tr" / "numbers.json")
                  .read_text(encoding="utf-8"))


def test_digits_and_words():
    assert numbers_in(TEXT["seven_days"]) == {7}
    assert numbers_in(TEXT["fifteen_days"]) == {15}
    assert numbers_in(TEXT["digits"]) == {30, 6}


def test_unsupported_numbers():
    assert unsupported_numbers(TEXT["claim_5"], [TEXT["seven_days"]]) == {5}
    assert unsupported_numbers(TEXT["claim_7_digits"], [TEXT["seven_days"]]) == set()


def test_joined_number_words_as_older_statutes_write_them():
    assert numbers_in(TEXT["joined"]) == {18, 24, 12}
    assert unsupported_numbers(TEXT["joined_claim"], [TEXT["joined"]]) == set()
    assert numbers_in(TEXT["hundreds"]) == {250, 1500}
    assert numbers_in(TEXT["eleven"]) == {11}


def test_words_that_only_look_like_numbers():
    assert numbers_in(TEXT["not_numbers"]) == set()


def test_fractions_in_words_and_digits():
    assert numbers_in(TEXT["fraction_words"]) == {0.25, 0.75}
    assert unsupported_numbers(TEXT["fraction_claim"], [TEXT["fraction_words"]]) == set()
    assert numbers_in(TEXT["sixth"]) == {1 / 6}
    assert numbers_in(TEXT["case_number"]) == {2025, 6036}


def test_quantities_become_digits_and_other_words_stay():
    assert digits_for_quantities(TEXT["quantity_words"]) == TEXT["quantity_digits"]
