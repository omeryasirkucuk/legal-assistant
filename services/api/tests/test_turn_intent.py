import pytest

from legal_api.agent import turn
from legal_api.agent.route import direct_intent
from legal_api.files.context import Attachment


@pytest.mark.parametrize("text", ["SELAM!", "  Merhaba 👋", "teşekkür ederim.", "Neler yapabilirsin?"])
async def test_direct_turn_keeps_pending_legal_work(text):
    holder = {}
    previous = turn.Previous("Dilekçe yaz", {"asked": True}, "Tarih nedir?")
    events = [e async for e in turn.turn_events(text, [], previous, holder,
              attachments=[Attachment("matter", "text/plain", "Earlier case")], explicit_files=False)]
    result = holder["result"]
    assert result.structure()["task"] == "direct"
    assert result.checked is None and result.usage.cost_usd == 0
    assert [e.type for e in events][-2:] == ["delta", "final"]
    assert events[-1].data["text"] == result.text


@pytest.mark.parametrize("text", ["Selam, kıdemim ne kadar?", "Teşekkürler, tabloya çevir",
                                  "Selam hakkında şikayet dilekçesi", "23 ay", "200 bin değil 150 bin"])
def test_mixed_messages_and_facts_stay_in_legal_routing(text):
    assert direct_intent(text) is None


@pytest.mark.parametrize("kind,message,expected_context,asked", [
    ("new", "Miras nasıl paylaşılır?", False, False),
    ("followup", "İşveren dün feshetti.", True, True),
    ("contextual", "Tarih dün.", True, True),
])
async def test_pending_draft_only_continues_for_related_messages(monkeypatch, kind, message,
                                                                 expected_context, asked):
    previous = turn.Previous("Dilekçe hazırla", {"asked": True}, "Ne zaman feshedildi?")
    history = [{"role": "user", "content": previous.question}]
    async def classify(*args):
        return kind

    async def answer(question, context, result, **kwargs):
        assert context == (history if expected_context else [])
        assert kwargs["just_asked"] is asked
        assert question.endswith(message)
        assert (previous.question in question) is asked
        yield turn.Event("final", {})

    monkeypatch.setattr(turn, "route", classify)
    monkeypatch.setattr(turn, "answer_events", answer)
    events = [e async for e in turn.turn_events(message, history, previous, {})]
    assert events[-1].type == "final"


async def test_user_upload_with_greeting_reaches_document_pipeline(monkeypatch):
    attachment = Attachment("document", "text/plain", "facts")
    async def answer(question, history, result, **kwargs):
        assert kwargs["attachments"] == [attachment]
        yield turn.Event("final", {})

    monkeypatch.setattr(turn, "answer_events", answer)
    events = [e async for e in turn.turn_events("selam", [], None, {}, attachments=[attachment])]
    assert any(e.type == "route" and e.data["kind"] == "new" for e in events)


async def test_salary_correction_researches_the_existing_question(monkeypatch):
    previous = turn.Previous("23 ay çalıştım, brüt maaşım 200 bin.", {}, "Kıdem hesabı")
    correction = "Maaşım 150 bin olacaktı."
    async def classify(*args):
        return "followup"

    async def answer(question, history, result, **kwargs):
        assert question == correction
        assert f"<previous_question>{previous.question}</previous_question>" in kwargs["search_text"]
        assert f"<current_request>{correction}</current_request>" in kwargs["search_text"]
        yield turn.Event("final", {})

    monkeypatch.setattr(turn, "route", classify)
    monkeypatch.setattr(turn, "answer_events", answer)
    events = [e async for e in turn.turn_events(correction, [], previous, {})]
    assert events[-1].type == "final"


@pytest.mark.parametrize("kind", ["followup", "new"])
async def test_matter_facts_and_documents_follow_the_active_topic(monkeypatch, kind):
    from types import SimpleNamespace

    from legal_api.workspace.session import Context

    opening = "Ev olarak kiraya verdim."
    recent = "İşyeri olsaydı?"
    previous = turn.Previous(recent, {"case_turns": [opening, recent],
                                      "case_file_ids": ["contract", "deleted"]}, "Varsayımsal sonuç")
    history = [{"role": "user", "content": recent}, {"role": "assistant", "content": previous.short}]
    doc = SimpleNamespace(id="contract", name="Kira.txt", media_type="text/plain", text="Madde 8")
    other = SimpleNamespace(id="other", name="Başka dosya", text="Unrelated")
    context = Context([doc, other])
    message = "Gerçek sözleşmeye dönelim" if kind == "followup" else "Yeni bir miras dosyası"

    async def classify(_message, _question, _answer, _usage, earlier, _files):
        assert earlier == [opening, recent]
        return kind

    async def answer(question, turns, result, **kwargs):
        active = kind == "followup"
        assert question == message
        assert (opening in [t["content"] for t in turns]) is active
        assert [f.text for f in kwargs["attachments"] or []] == (["Madde 8"] if active else [])
        result["result"] = SimpleNamespace(trace={})
        yield turn.Event("final", {})

    monkeypatch.setattr(turn, "route", classify)
    monkeypatch.setattr(turn, "answer_events", answer)
    holder = {}
    _ = [e async for e in turn.turn_events(message, history, previous, holder, workspace=context)]
    assert holder["result"].case_turns == ([opening, recent, message] if kind == "followup" else [message])


def test_memory_bounds_preserve_opening_and_latest_correction():
    messages = ["İlk olay", *(f"Açıklama {i}" for i in range(14)), "Son düzeltme"]
    kept = turn.case_turns(turn.Previous(messages[-1], {"case_turns": messages[:-1]}, ""), [])
    assert len(kept) == 10
    assert kept[0] == messages[0] and kept[-1] == messages[-1]
