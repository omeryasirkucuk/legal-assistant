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
