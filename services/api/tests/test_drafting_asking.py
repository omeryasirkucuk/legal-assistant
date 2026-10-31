from legal_api.drafting.asking import ASK_AT, Gaps, kind_of, record, should_ask, threshold
from legal_api.drafting.cases import case_kinds, general_kind

QUESTION = [{"question": "q", "options": []}]


def test_every_case_kind_has_essential_facts_and_a_length():
    for kind in [*case_kinds().values(), general_kind()]:
        assert kind.critical and kind.helpful and kind.words > 0, kind.id
    assert kind_of("no-such-kind") == general_kind()


def test_asks_only_when_enough_essential_facts_are_missing():
    kind = kind_of("bosanma")
    assert should_ask(Gaps(ASK_AT, QUESTION), kind, {}, False, False)
    assert not should_ask(Gaps(ASK_AT - 0.5, QUESTION), kind, {}, False, False)


def test_never_asks_twice_in_a_row_or_when_told_to_write():
    kind = kind_of("bosanma")
    many = Gaps(3, QUESTION)
    assert not should_ask(many, kind, {}, write_now=True, just_asked=False)
    assert not should_ask(many, kind, {}, write_now=False, just_asked=True)


def test_the_lawyers_habit_moves_the_threshold():
    skips = record(record({}, skipped=True), skipped=True)
    answers = record(record({}, skipped=False), skipped=False)
    assert threshold(skips, 3) == 3 and threshold(answers, 3) < ASK_AT
    kind = kind_of("bosanma")
    assert not should_ask(Gaps(2.5, QUESTION), kind, skips, False, False)
    assert should_ask(Gaps(1.5, QUESTION), kind, answers, False, False)
