from datetime import date

from legal_api.calc.deadlines import add_period, compute


def test_periods_in_days_weeks_and_months():
    assert add_period(date(2026, 3, 3), 7, "day") == date(2026, 3, 10)
    assert add_period(date(2026, 3, 3), 2, "week") == date(2026, 3, 17)
    assert add_period(date(2026, 1, 31), 1, "month") == date(2026, 2, 28)
    assert add_period(date(2026, 11, 15), 3, "month") == date(2027, 2, 15)


def test_a_last_day_on_a_weekend_or_holiday_moves_to_the_next_working_day():
    # 2 weeks from 2026-03-07 ends Saturday 21 March, inside the Ramadan holiday (20-22).
    d = compute(date(2026, 3, 7), 2, "week", recess=False)
    assert d.end == date(2026, 3, 23) and d.steps[-1][0] == "holiday"
    # 1 week from Friday 2026-10-02 ends Friday 9 October: a working day.
    assert compute(date(2026, 10, 2), 1, "week", recess=False).end == date(2026, 10, 9)


def test_the_judicial_recess_extends_a_period_ending_in_it():
    d = compute(date(2026, 7, 10), 2, "week", recess=True)   # would end 24 July
    assert d.end == date(2026, 9, 7) and d.steps[1][0] == "recess"
    assert compute(date(2026, 7, 10), 2, "week", recess=False).end == date(2026, 7, 24)


def test_half_day_eves_and_uncovered_years_are_flagged():
    d = compute(date(2026, 10, 21), 7, "day", recess=False)   # ends 28 October, eve
    assert d.end == date(2026, 10, 28) and d.warnings[0][0] == "half_day"
    assert compute(date(2027, 12, 1), 2, "month", recess=False).warnings[0][0] == "not_covered"


def test_the_period_length_is_checked_against_the_article_and_written_out():
    from legal_api.calc.sources import render, states_length
    article = "İstinaf yoluna başvuru süresi iki haftadır. Bu süre kararın tebliği ile başlar."
    assert states_length(article, 2, "week") and not states_length(article, 1, "month")
    assert states_length("Borçlu yedi gün içinde itiraz edebilir.", 7, "day")
    d = compute(date(2026, 3, 7), 2, "week", recess=False)
    text = render("İstinaf", d, "HMK m. 345", True)
    assert "23.03.2026 Pazartesi" in text.splitlines()[-1] and "Ramazan Bayramı" in text
