import asyncio
from datetime import UTC, datetime

from legal_api import llm
from legal_api.agent import screen as screen_module
from legal_api.retrieval.statutes import StatuteHit


def _hit(label: str) -> StatuteHit:
    return StatuteHit(1, "2004", "Enforcement Law", "s", label, "heading", "text", "u",
                      datetime.now(UTC))


def test_without_decision_model_every_candidate_is_left_for_review(monkeypatch):
    monkeypatch.setattr(screen_module.decisions, "enabled", lambda: False)
    out = asyncio.run(screen_module.screen("q", [_hit("62"), _hit("168")], llm.Usage()))
    assert all(not s.answers and not s.rejected for s in out)


def test_probabilities_split_candidates(monkeypatch):
    probabilities = {"62": 0.96, "65": 0.47, "156": 0.24, "9": None}

    async def fake(client, state, questions, usage, purpose):
        return {"answers": probabilities[state["article"].split("art. ")[1].split(" ")[0]]}

    monkeypatch.setattr(screen_module.decisions, "enabled", lambda: True)
    monkeypatch.setattr(screen_module.decisions, "yes_probabilities", fake)
    out = asyncio.run(screen_module.screen("q", [_hit(k) for k in probabilities], llm.Usage()))
    by_label = {s.hit.label: s for s in out}
    assert by_label["62"].answers
    assert not by_label["65"].answers and not by_label["65"].rejected
    assert by_label["156"].rejected
    assert not by_label["9"].answers and not by_label["9"].rejected  # service failure: review


async def test_amount_research_keeps_explicit_precedent_search(monkeypatch):
    from unittest.mock import AsyncMock

    from legal_api.agent import research
    from legal_api.agent.understand import Understanding

    candidates = AsyncMock(return_value=research.Candidates([], set(), []))
    monkeypatch.setattr(research, "candidates", candidates)
    monkeypatch.setattr(research, "screen", AsyncMock(return_value=[]))
    related_statutes = AsyncMock(return_value=[])
    monkeypatch.setattr(research, "nearby", related_statutes)
    monkeypatch.setattr(research, "siblings", related_statutes)
    monkeypatch.setattr(research, "follow_references", AsyncMock(return_value=[]))
    precedents = AsyncMock(return_value=[])

    class Finder:
        decisions_for = precedents

    understand = Understanding(task="consultation", shape="amount")
    for query in ("", "fesih ve tazminat"):
        understand.case_law_query = query
        await research.research(None, Finder(), "Hesapla", understand, llm.Usage(),
                                lambda *_args, **_kwargs: None)
        assert candidates.call_args.kwargs["per_query"] < research.PER_QUERY

    assert not related_statutes.await_count
    assert precedents.await_count == 1
    assert precedents.await_args.args[0] == "fesih ve tazminat"
    understand.requested_precedents = True
    await research.research(None, Finder(), "Hem hesap hem emsal", understand, llm.Usage(),
                            lambda *_args, **_kwargs: None)
    assert precedents.await_args.kwargs["precedents"] is True
