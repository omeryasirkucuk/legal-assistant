import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from legal_api import llm
from legal_api.agent import case_law, research
from legal_api.agent.understand import Understanding
from legal_api.sources.types import Court, Decision, DecisionRef


def ref(identifier: str) -> DecisionRef:
    return DecisionRef(identifier, Court.YARGITAY, "6. HD", None, None, None, "")


async def test_supplemental_lookup_keeps_decisions_fetched_before_timeout(monkeypatch):
    class Source:
        async def search(self, query, *, size):
            return 2, [ref("first"), ref("second")]

        async def fetch(self, decision):
            if decision.source_id == "second":
                await asyncio.Future()
            return Decision(decision, "First decision")

    monkeypatch.setattr(case_law, "SUPPLEMENTAL_LIVE_BUDGET_S", 0)
    result = await case_law._live(Source(), "test query", "question", supplemental=True)

    assert [decision.passage for decision in result] == ["First decision"]


async def test_queries_preserve_constraints_and_interleave_unique_results():
    queried = []
    fetched = []

    class Source:
        async def search(self, query, *, size):
            queried.append(query)
            matches = {"kira borcu örnek 13": ["1", "2"], "kira bedeli itiraz": ["1", "3", "4"]}
            return 100, [ref(s) for s in matches[query]]

        async def fetch(self, decision):
            fetched.append(decision.source_id)
            return Decision(decision, decision.source_id)

    await case_law._live(Source(), "kira borcu örnek 13", "kira borcu",
                         alternative="kira bedeli itiraz", limit=3)

    assert queried == ["kira borcu örnek 13", "kira bedeli itiraz"]
    assert fetched == ["1", "2", "3"]


async def test_match_requires_the_holding_and_every_condition(monkeypatch):
    @asynccontextmanager
    async def client():
        yield None

    async def judge(_client, state, checks, _usage, _purpose):
        assert state["required_conditions"] == ("ana kira borcu", "hiç ödeme yok")
        full = dict.fromkeys(checks, 0.91)
        return {
            "exact": {**full, "direct": 0.78, "holding": 0.83},
            "partial payment": {**full, "condition_1": 0.04, "related": 0.97},
            "quoted lower court": {**full, "holding": 0.08, "related": 0.93},
            "unrelated": {**full, "direct": 0.05, "related": 0.22},
        }[state["decision_passages"]]

    monkeypatch.setattr(case_law.decisions, "enabled", lambda: True)
    monkeypatch.setattr(case_law.decisions, "client", client)
    monkeypatch.setattr(case_law.decisions, "yes_probabilities", judge)
    passages = [case_law.Passage(name, name) for name in
                ("partial payment", "unrelated", "exact", "quoted lower court")]
    requirements = ("ana kira borcu", "hiç ödeme yok")
    filtered = await case_law._screen("case", passages, llm.Usage(), 4, strict=True,
                                      requirements=requirements, include_related=True)
    draft = await case_law._screen("case", passages, llm.Usage(), 4, strict=True,
                                   requirements=requirements, include_related=False)

    assert [(p.passage, p.match) for p in filtered] == [
        ("exact", "direct"), ("partial payment", "related"), ("quoted lower court", "related")]
    assert [(p.passage, p.match) for p in draft] == [("exact", "direct")]


async def test_slow_decision_does_not_erase_other_completed_verdicts(monkeypatch):
    @asynccontextmanager
    async def client():
        yield None

    async def judge(_client, state, checks, _usage, _purpose):
        if state["decision_passages"] == "slow":
            await asyncio.Future()
        return dict.fromkeys(checks, 0.99)

    monkeypatch.setattr(case_law.decisions, "enabled", lambda: True)
    monkeypatch.setattr(case_law.decisions, "client", client)
    monkeypatch.setattr(case_law.decisions, "yes_probabilities", judge)
    monkeypatch.setattr(case_law, "DECISION_CHECK_S", 0)
    passages = [case_law.Passage(name, name) for name in ("completed", "slow")]

    result = await case_law._screen("case", passages, llm.Usage(), 2, strict=True,
                                    requirements=("ana kira borcu",), include_related=True)
    assert [(p.passage, p.match) for p in result] == [("completed", "direct")]


async def test_draft_research_runs_one_case_pass_alongside_statutes(monkeypatch):
    calls = []
    statute_started = asyncio.Event()

    async def statutes(*_args):
        statute_started.set()
        await decision_started.wait()
        return research.Research()

    decision_started = asyncio.Event()

    async def fetch(query, ask, usage, **options):
        await statute_started.wait()
        decision_started.set()
        calls.append((query, options))
        return []

    monkeypatch.setattr(research, "_statute_sources", statutes)
    understanding = Understanding(task="drafting", case_law_query="kira borcu",
                                  case_law_alternative="kira bedeli",
                                  case_law_requirements=["hiç ödeme yok"],
                                  issues=[("İtiraz", "ödeme emrine itiraz")] * 4)
    async with asyncio.timeout(1):
        result = await research.research(None, SimpleNamespace(decisions_for=fetch),
                                         "draft", understanding, llm.Usage(), lambda *a, **k: None)

    assert len(calls) == 1
    assert calls[0][0] == "kira borcu"
    assert calls[0][1]["requirements"] == ("hiç ödeme yok",)
    assert calls[0][1]["alternative"] == "kira bedeli"
    assert calls[0][1]["include_related"] is False
    assert result.trace["direct_decisions"] == 0
    assert result.trace["case_law_searched"] is True


def test_case_plan_preserves_legacy_queries_and_keeps_separate_conditions():
    from legal_api.agent.understand import _case_plan

    assert _case_plan("kira tahliye") == ("kira tahliye", "", [])
    assert _case_plan("") == ("", "", [])
    assert _case_plan(
        "kira borcu tahliye\nalternatif: kira bedeli örnek 13\n"
        "koşul: itiraz yok\nkoşul: kısmi ödeme yok\nkoşul: itiraz yok"
    ) == ("kira borcu tahliye", "kira bedeli örnek 13", ["itiraz yok", "kısmi ödeme yok"])


async def test_local_decision_survives_a_live_rate_limit(monkeypatch):
    from legal_api.sources.gateway import SourceBlocked

    class BlockedSource:
        async def search(self, query, *, size):
            raise SourceBlocked("rate limited")

    async def archived(_conn, query, _excerpt_query):
        assert "kira bedeli" in query
        return [case_law.Passage("local passage", "local full text", live=Decision(
            ref("archive"), "local full text"))]

    async def screen(_ask, passages, _usage, _keep, **_options):
        return passages

    monkeypatch.setattr(case_law, "_local", archived)
    monkeypatch.setattr(case_law, "_screen", screen)

    result = await case_law.case_passages(None, BlockedSource(), "kira borcu", "case",
                                          llm.Usage(), alternative="kira bedeli")
    assert [p.passage for p in result] == ["local passage"]


def test_decision_passage_keeps_majority_disposition_and_excludes_dissent():
    text = (
        "Somut olayda alacak kira bedeline ilişkindir.\n\n"
        "IV. SONUÇ: Hükmün incelenmek üzere bozulmasına karar verildi.\n\n"
        "KARŞI OY \n"
        "İtiraz ve ödeme konusunda çoğunluğun aksine tahliye gerekir."
    )

    excerpt = case_law._closest_passage(text, "itiraz ödeme tahliye")
    assert "bozulmasına karar verildi" in excerpt
    assert "tahliye gerekir" not in excerpt
