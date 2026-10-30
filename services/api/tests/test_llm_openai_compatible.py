import json

import httpx
import pytest

from legal_api import llm
from legal_api.agent.atoms import openai_segments_from
from legal_api.config import Settings


def _settings() -> Settings:
    return Settings(llm_provider="openai_compatible", openai_api_key="test-token",
                    openai_base_url="http://openwebui.test/api",
                    openai_model_main="local/legal-model")


def test_openai_answer_requires_a_known_source_key():
    sources = [("E1", "Enforcement Law art. 62", "The debtor may object within seven days.")]
    good = 'Seven days. <quote ref="E1">may object within seven days</quote>[[E1]]'
    bad_key = 'Five days. <quote ref="E9">may object within seven days</quote>[[E9]]'
    bad_quote = 'Five days. <quote ref="E1">objects within five days</quote>[[E1]]'
    assert openai_segments_from([llm.TextBlock("text", good)], sources)[0].keys == ("E1",)
    assert openai_segments_from([llm.TextBlock("text", bad_key)], sources) == []
    assert openai_segments_from([llm.TextBlock("text", bad_quote)], sources) == []
    assert openai_segments_from([llm.TextBlock("text", "Seven days [[E1]]")], sources) == []


@pytest.mark.asyncio
async def test_openwebui_create_uses_api_route_and_normalizes_response(monkeypatch):
    settings = _settings()
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "local/legal-model",
            "choices": [{"message": {"content": "Seven days [[E1]]"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "cost": 0.002},
        })

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "openai_client", lambda: httpx.AsyncClient(
        base_url=settings.openai_base_url, headers={"authorization": "Bearer test-token"},
        transport=transport))
    usage = llm.Usage()
    result = await llm.create("main", usage, "test", max_tokens=100,
                              system="Grounded answer.",
                              messages=[{"role": "user", "content": "Question"}],
                              output_config={"format": {"type": "json_schema", "schema": {
                                  "type": "object", "properties": {"answer": {"type": "string"}},
                                  "required": ["answer"], "additionalProperties": False,
                              }}})

    assert seen["path"] == "/api/chat/completions"
    assert seen["authorization"] == "Bearer test-token"
    assert seen["payload"]["model"] == "local/legal-model"
    assert seen["payload"]["response_format"]["json_schema"]["strict"] is True
    assert result.content[0].text == "Seven days [[E1]]"
    assert result.usage.input_tokens == 12
    assert usage.cost_usd == 0.002


@pytest.mark.asyncio
async def test_openai_stream_yields_text_and_final_usage(monkeypatch):
    settings = _settings()
    body = (
        'data: {"model":"local/legal-model","choices":[{"delta":{"content":"Seven "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"days [[E1]]"},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":3}}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat/completions"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "openai_client", lambda: httpx.AsyncClient(
        base_url=settings.openai_base_url, transport=transport))
    usage = llm.Usage()
    items = [item async for item in llm.stream(
        "main", usage, "detail", max_tokens=100,
        messages=[{"role": "user", "content": "Question"}],
    )]

    assert items[:-1] == ["Seven ", "days [[E1]]"]
    assert items[-1].content[0].text == "Seven days [[E1]]"
    assert items[-1].usage.input_tokens == 8
    assert usage.calls[0]["output"] == 3
