import uuid
from datetime import date

from legal_api.agent.pipeline import _calendar_only
from legal_api.agent.understand import Understanding
from legal_api.db.matter_models import Matter, MatterDeadline
from legal_api.grounding.evidence import EvidenceLedger
from legal_api.locale import matter_terms
from legal_api.matters.agenda import Agenda, render

TODAY = date(2026, 11, 2)       # a Monday
T = matter_terms()["agenda"]


def _matter(client: str, case_no: str = "") -> Matter:
    return Matter(id=uuid.uuid4(), client=client, case_no=case_no, closed=False)


def _deadline(m: Matter, label: str, due: date, done: bool = False,
              branch: str | None = None) -> MatterDeadline:
    return MatterDeadline(id=uuid.uuid4(), matter_id=m.id, label=label, due=due, done=done,
                          branch=branch)


def test_the_calendar_lists_open_deadlines_with_their_cases_and_days_left():
    a, b = _matter("Client A", "2026/12"), _matter("Client B")
    rows = [(_deadline(a, "Appeal", date(2026, 10, 30)), a),
            (_deadline(b, "Reply", date(2026, 11, 2)), b),
            (_deadline(a, "Hearing", date(2026, 11, 9), branch="civil"), a),
            (_deadline(b, "Filed", date(2026, 11, 20), done=True), b)]
    text = render(rows, TODAY)
    lines = text.splitlines()
    assert lines[-3].startswith("30.10.2026") and "Appeal (Client A, 2026/12)" in lines[-3]
    assert T["passed"].format(days=3) in lines[-3]
    assert "Reply (Client B)" in lines[-2] and T["today"] in lines[-2]
    assert T["left"].format(days=7) in lines[-1]
    assert T["branch"].format(branch=T["branches"]["civil"]) in lines[-1]
    assert "Filed" not in text


def test_in_a_case_only_its_own_deadlines_are_listed():
    a, b = _matter("Client A"), _matter("Client B")
    rows = [(_deadline(b, "Other reply", date(2026, 11, 3)), b),
            (_deadline(a, "Filed", date(2026, 11, 4), done=True), a),
            (_deadline(a, "Appeal", date(2026, 11, 5)), a)]
    text = render(rows, TODAY, a)
    assert "Filed" in text and T["done"] in text and "Appeal" in text
    assert "Other reply" not in text and "Client B" not in text


def test_an_empty_calendar_says_so():
    assert T["none"] in render([], TODAY)
    assert T["none_matter"] in render([], TODAY, _matter("Client A"))


def test_the_calendar_becomes_a_cited_source():
    ledger = EvidenceLedger()
    source = Agenda("listing", T["citation"], "agenda:all").source(ledger)
    assert source.evidence.citation == T["citation"] and source.document == "listing"


def test_only_a_pure_calendar_question_skips_the_statute_search():
    agenda = Agenda("listing", "c", "agenda:all")
    assert _calendar_only(Understanding(calendar=True), agenda)
    assert not _calendar_only(Understanding(calendar=True), None)
    assert not _calendar_only(Understanding(calendar=True,
                                            issues=[("appeal period", "appeal period")]), agenda)
    assert not _calendar_only(Understanding(), agenda)
