import asyncio
import json
from types import SimpleNamespace

from legal_api import llm
from legal_api.agent import compose as compose_module
from legal_api.agent.route import route

STRUCTURE = {"branches": [
    {"label": "Bills", "atoms": [
        {"ask": "period?", "found": True, "segments": [{"text": "within 5 days", "keys": ["E1"]}]},
        {"ask": "late?", "found": True, "segments": [{"text": "3 days after", "keys": ["E2"]}]}]},
    {"label": "General", "atoms": [
        {"ask": "period?", "found": True, "segments": [{"text": "7 days", "keys": ["E3"]}]}]},
    {"label": "Pledge", "atoms": [{"ask": "period?", "found": False, "segments": []}]},
]}


def _fake_model(gists_by_label):
    """Per-branch calls: answers with the gists given for the branch in the request."""
    async def create(*args, **kwargs):
        content = kwargs["messages"][0]["content"]
        gists = next((g for label, g in gists_by_label.items() if f"] {label}" in content), [])
        return SimpleNamespace(content=[SimpleNamespace(type="text",
                                                        text=json.dumps({"gists": gists}))])
    return create


def test_every_found_sub_answer_is_in_its_branch_line(monkeypatch):
    monkeypatch.setattr(compose_module.llm, "create", _fake_model({
        "Bills": [{"branch": "B1", "atom": "A1", "gist": "5 days"}],
        "General": [{"branch": "[1]", "atom": "A1", "gist": "7 days"}]}))
    lines = asyncio.run(compose_module.compose("q", STRUCTURE, llm.Usage()))
    # B1/A2 got no gist: its sub-answer is used as it is, not dropped.
    assert [(ln.text, ln.keys) for ln in lines] == [
        ("Bills: 5 days; 3 days after", ("E1", "E2")), ("General: 7 days", ("E3",))]
    assert "[[E1]]" in compose_module.short_text(lines)


def test_a_gist_with_an_unsupported_number_falls_back(monkeypatch):
    monkeypatch.setattr(compose_module.llm, "create", _fake_model({
        "Bills": [{"branch": "Bills", "atom": "A1", "gist": "10 days"}]}))
    lines = asyncio.run(compose_module.compose("q", STRUCTURE, llm.Usage()))
    assert lines[0].text == "Bills: within 5 days; 3 days after"
    assert not lines[0].composed


def test_without_a_previous_answer_every_message_is_new():
    assert asyncio.run(route("shorter please", None, None, llm.Usage())) == "new"


def test_without_a_decision_model_a_message_after_an_answer_is_a_followup(monkeypatch):
    monkeypatch.setattr("legal_api.agent.route.decisions.enabled", lambda: False)
    assert asyncio.run(route("shorter please", "q", "a", llm.Usage())) == "followup"


def test_no_cited_line_says_nothing_was_found():
    from legal_api.locale import message
    assert compose_module.short_text([]) == message("status", "no_answer")


def test_layout_and_citation_numbers_are_not_quantities():
    from legal_api.agent.write import without_citations
    from legal_api.grounding.numbers import numbers_in
    text = "### 2. Heading\n1. **Route (TBK m. 352/2):** E. 2019/1483, 25.06.2019: 7 days"
    assert numbers_in(without_citations(text)) == {7}
