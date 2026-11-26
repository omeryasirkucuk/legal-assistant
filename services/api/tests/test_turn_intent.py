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
