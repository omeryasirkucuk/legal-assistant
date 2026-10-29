import httpx
import pytest

from legal_api.sources.gateway import Gateway, SourceBlocked, SourceError


def _gateway(handler) -> Gateway:
    return Gateway(transport=httpx.MockTransport(handler), min_interval=0, shared=False)


async def test_rate_limit_puts_host_on_cooldown_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "30"})

    gw = _gateway(handler)
    with pytest.raises(SourceBlocked) as first:
        await gw.json("GET", "https://example.test/a", source="x")
    assert first.value.retry_after == 30
    with pytest.raises(SourceBlocked):
        await gw.json("GET", "https://example.test/b", source="x")
    assert len(calls) == 1


async def test_html_instead_of_json_is_a_block():
    gw = _gateway(lambda r: httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(SourceBlocked):
        await gw.json("GET", "https://example.test/", source="x")


async def test_captcha_flag_is_a_block():
    gw = _gateway(lambda r: httpx.Response(200, json={"isDisplayCaptcha": True}))
    with pytest.raises(SourceBlocked):
        await gw.json("GET", "https://example.test/", source="x")


async def test_word_captcha_inside_decision_text_is_not_a_block():
    gw = _gateway(lambda r: httpx.Response(200, json={"text": "the captcha was mentioned"}))
    assert (await gw.json("GET", "https://example.test/", source="x"))["text"]


async def test_server_error_is_source_error_without_cooldown():
    responses = iter([httpx.Response(503), httpx.Response(200, json={"ok": True})])
    gw = _gateway(lambda r: next(responses))
    with pytest.raises(SourceError) as exc:
        await gw.json("GET", "https://example.test/", source="x")
    assert not isinstance(exc.value, SourceBlocked)
    assert await gw.json("GET", "https://example.test/", source="x") == {"ok": True}


async def test_requests_identify_the_client():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json={})

    await _gateway(handler).json("GET", "https://example.test/", source="x")
    assert seen["ua"].startswith("legal-assistant/")


async def test_rate_limit_state_is_shared_across_gateways():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    first = Gateway(transport=httpx.MockTransport(handler), min_interval=0)
    second = Gateway(transport=httpx.MockTransport(handler), min_interval=0)
    with pytest.raises(SourceBlocked):
        await first.json("GET", "https://shared-limit.test/a", source="x")
    with pytest.raises(SourceBlocked):
        await second.json("GET", "https://shared-limit.test/b", source="x")
    assert len(calls) == 1
