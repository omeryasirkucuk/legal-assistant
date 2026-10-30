from datetime import UTC, datetime

from legal_api.agent.candidates import Candidates
from legal_api.agent.decompose import Atom, Branch, _attach_references
from legal_api.agent.follow import Followed
from legal_api.retrieval.statutes import StatuteHit

LAWS = {"2004": "Enforcement Law", "6098": "Code of Obligations"}


def _hit(i: int, law: str, label: str) -> StatuteHit:
    return StatuteHit(i, law, LAWS[law], "s", label, "heading", "text", "u", datetime.now(UTC))


def _candidates() -> Candidates:
    referring = _hit(1, "2004", "269")
    return Candidates(referenced=[Followed(_hit(2, "6098", "315"), referring, "sentence"),
                                  Followed(_hit(3, "6098", "352"), referring, "sentence")],
                      laws=LAWS)


def test_reference_becomes_a_sub_question_in_the_citing_branch():
    branches = [Branch("other", [Atom("q0", (("2004", "62"),), "")]),
                Branch("rent", [Atom("q1", (("2004", "269"),), "")])]
    review = [{"id": "R1", "branch": "no such label", "ask": "payment period?"},
              {"id": "R2", "branch": "", "ask": ""}]
    _attach_references(branches, review, _candidates())
    assert [a.ask for a in branches[1].atoms] == ["q1", "payment period?"]
    assert branches[1].atoms[1].statutes == (("6098", "315"), ("2004", "269"))
    assert len(branches[0].atoms) == 1


def test_named_branch_wins_and_unknown_ids_are_ignored():
    branches = [Branch("rent", [Atom("q1", (("2004", "62"),), "")])]
    review = [{"id": "R1", "branch": "rent", "ask": "a"},
              {"id": "R9", "branch": "rent", "ask": "b"}]
    _attach_references(branches, review, _candidates())
    assert [a.ask for a in branches[0].atoms] == ["q1", "a"]


def test_screened_articles_left_out_of_the_plan_get_a_sub_question():
    from legal_api.agent.decompose import _cover_answering
    candidates = Candidates(answering=[_hit(4, "2004", "62"), _hit(5, "2004", "150")], laws=LAWS)
    branches = [Branch("general", [Atom("q0", (("2004", "62"),), "")])]
    review = [{"article": "Law 2004 art. 150", "answers_question": True, "situation": "pledge"}]
    _cover_answering(branches, "objection period?", review, candidates)
    assert [(b.label, [a.ask for a in b.atoms]) for b in branches] == [
        ("general", ["q0"]), ("pledge", ["pledge: objection period?"])]


def test_an_article_the_planner_rejected_is_not_forced_in():
    from legal_api.agent.decompose import _cover_answering
    candidates = Candidates(answering=[_hit(5, "2004", "89")], laws=LAWS)
    branches = [Branch("general", [Atom("q0", (("2004", "62"),), "")])]
    review = [{"article": "Law 2004 art. 89", "answers_question": False, "situation": "x"}]
    _cover_answering(branches, "objection period?", review, candidates)
    assert [b.label for b in branches] == ["general"]


def test_left_out_articles_on_the_same_situation_share_one_sub_question():
    from legal_api.agent.decompose import _cover_answering
    candidates = Candidates(answering=[_hit(4, "2004", "60"), _hit(5, "2004", "62")], laws=LAWS)
    branches = [Branch("bills", [Atom("q0", (("2004", "168"),), "")])]
    review = [{"article": "Law 2004 art. 60", "answers_question": True, "situation": "general"},
              {"article": "Law 2004 art. 62", "answers_question": True, "situation": "General"}]
    _cover_answering(branches, "period?", review, candidates)
    assert [(b.label, [a.statutes for a in b.atoms]) for b in branches] == [
        ("bills", [(("2004", "168"),)]), ("general", [(("2004", "60"), ("2004", "62"))])]
