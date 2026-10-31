from datetime import date

from legal_api.calc.notice import from_notice


def test_electronic_service_counts_from_the_fifth_day():
    r = from_notice(date(2026, 11, 2), "electronic", 2, "week", "civil")
    assert r.served == date(2026, 11, 7)
    assert r.deadline.end == date(2026, 11, 23)        # 21 Nov is a Saturday


def test_the_recess_extends_by_branch():
    civil = from_notice(date(2026, 7, 20), "hearing", 2, "week", "civil")
    criminal = from_notice(date(2026, 7, 20), "hearing", 2, "week", "criminal")
    enforcement = from_notice(date(2026, 7, 20), "physical", 7, "day", "enforcement")
    assert civil.deadline.end == date(2026, 9, 7)
    assert criminal.deadline.end == date(2026, 9, 3)
    assert enforcement.deadline.end == date(2026, 7, 27)
    assert "detention" in criminal.notes

