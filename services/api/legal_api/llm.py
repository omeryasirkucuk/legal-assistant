"""Anthropic and OpenAI-compatible clients with per-role models and usage accounting.

Anthropic requests use the server-side refusal fallback; OpenAI-compatible requests use
the standard chat-completions endpoint and verified, exact source-quote citations.
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal

import anthropic
import httpx

from legal_api.config import get_settings

Role = Literal["main", "draft", "cheap", "judge", "write"]
FALLBACK_BETA = "server-side-fallback-2026-07-01"

REQUEST_TIMEOUT_S = 120.0
CACHE_WRITE_MULTIPLIER = 1.25  # 5-minute cache writes cost 1.25x base input

# USD per million tokens (input, output, cache read). Source: Anthropic pricing, 2026-10.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
# Haiku 5.5 prompts above 100K tokens are billed at a higher rate.
LONG_PROMPT_TOKENS = 100_000
LONG_PROMPT_PRICES: dict[str, tuple[float, float, float]] = {
    "claude-haiku-5-5": (0.50, 2.50, 0.05),
}


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str
    base_url: str
    api_key: str
    model_main: str
    model_draft: str
    model_cheap: str
    model_judge: str


_runtime_config: ContextVar[RuntimeConfig | None] = ContextVar("llm_runtime_config", default=None)


def set_runtime_config(config: RuntimeConfig | None) -> Token:
    return _runtime_config.set(config)


def reset_runtime_config(token: Token) -> None:
    _runtime_config.reset(token)


def _connection(settings) -> RuntimeConfig | None:
    if settings.protected_data:
        return RuntimeConfig(
            "openai_compatible", settings.private_model_base_url, settings.private_model_api_key,
            settings.openai_model_main, settings.openai_model_draft, settings.openai_model_cheap,
            settings.openai_model_judge,
        )
    return _runtime_config.get()


def model_for(role: Role) -> str:
    s = get_settings()
    configured = _connection(s)
    if configured:
        return {"main": configured.model_main, "draft": configured.model_draft,
                "cheap": configured.model_cheap, "judge": configured.model_judge,
                "write": configured.model_main}[role]
    if uses_openai_compatible(s):
        return {"main": s.openai_model_main, "draft": s.openai_model_draft,
                "cheap": s.openai_model_cheap, "judge": s.openai_model_judge,
                "write": s.openai_model_main}[role]
    return {"main": s.model_main, "draft": s.model_draft, "cheap": s.model_cheap,
            "judge": s.model_judge, "write": s.model_write}[role]


def uses_openai_compatible(settings=None) -> bool:
    settings = settings or get_settings()
    configured = _connection(settings)
    provider_value = configured.provider if configured else settings.llm_provider
    provider = provider_value.strip().casefold().replace("-", "_")
    return provider in {"openai", "openai_compatible", "openwebui", "open_webui"}


def routed(role: Role) -> str | None:
    """The OpenRouter model a role is sent to instead of the configured provider, if any:
    the answer writer ("write") and the petition writer ("draft"), or with
    ANTHROPIC_VIA_OPENROUTER every role, to the same Anthropic model there."""
    s = get_settings()
    if _connection(s) or not s.decision_api_key:
        return None
    explicit = {"write": s.write_route, "draft": s.draft_route}.get(role)
    if explicit:
        return explicit
    if s.anthropic_via_openrouter and not uses_openai_compatible(s):
        return openrouter_id(model_for(role))
    return None


def openrouter_id(model: str) -> str:
    """OpenRouter's name for an Anthropic model: claude-sonnet-5-5 -> anthropic/claude-sonnet-5.5."""
    return "anthropic/" + re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", model)


def openai_for(role: Role) -> bool:
    """Whether this role is served by an OpenAI-compatible endpoint (no document citations)."""
    return uses_openai_compatible() or routed(role) is not None


@cache
def client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    if settings.llm_provider != "anthropic":
        raise NotImplementedError(f"provider {settings.llm_provider!r} is not wired yet")
    # The SDK default (10 minutes, retried twice) let a stalled request hold an answer for
    # half an hour; no call here needs more than two minutes between bytes.
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None,
                                    timeout=REQUEST_TIMEOUT_S,
                                    max_retries=1)


def openai_client(route: bool = False) -> httpx.AsyncClient:
    """HTTP client for OpenAI-compatible services, including Open WebUI's /api endpoint;
    `route`: OpenRouter, for a role routed there (see `routed`)."""
    settings = get_settings()
    configured = _connection(settings)
    headers = {"content-type": "application/json"}
    if route:
        api_key, base_url = settings.decision_api_key, settings.decision_base_url + "/v1"
    else:
        api_key = configured.api_key if configured else settings.openai_api_key
        base_url = configured.base_url if configured else settings.openai_base_url
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    return httpx.AsyncClient(base_url=base_url.rstrip("/"),
                             headers=headers, timeout=httpx.Timeout(180.0, connect=10.0),
                             trust_env=not settings.protected_data)


@dataclass
class CompletionUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost: float | None = None


@dataclass
class TextBlock:
    type: str
    text: str
    citations: list = field(default_factory=list)


@dataclass
class Completion:
    content: list[TextBlock]
    model: str
    usage: CompletionUsage
    stop_reason: str | None = None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "document":
            source = block.get("source", {})
            title = block.get("title", "Source")
            parts.append(f"\n<{title}>\n{source.get('data', '')}\n</{title}>\n")
    return "\n".join(parts)


def _openai_payload(model: str, params: dict, *, stream: bool = False,
                    route: bool = False) -> dict:
    params = dict(params)
    system = params.pop("system", None)
    params.pop("cache_control", None)
    output_config = params.pop("output_config", None)
    messages = params.pop("messages", [])
    formatted = []
    if system:
        formatted.append({"role": "system", "content": system})
    for message in messages:
        formatted.append({"role": message["role"], "content": _content_text(message.get("content"))})
    payload = {"model": model, "messages": formatted, **params}
    if output_config and output_config.get("format", {}).get("type") == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "legal_assistant_response", "strict": True,
                             "schema": output_config["format"]["schema"]},
        }
    if route:
        # No host that may keep or train on the lawyer's text; the cost comes back per call.
        payload["provider"] = {"data_collection": "deny"}
        payload["usage"] = {"include": True}
        # Reasoning models count their thinking in max_tokens: left at their default, one
        # spent all 16,000 tokens thinking and wrote no petition. The answer's effort is used.
        if output_config and output_config.get("effort"):
            payload["reasoning"] = {"effort": output_config["effort"]}
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    return payload


def _openai_completion(data: dict) -> Completion:
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message", {})
    usage = data.get("usage") or {}
    return Completion(
        content=[TextBlock("text", message.get("content") or "")],
        model=data.get("model") or "",
        usage=CompletionUsage(input_tokens=usage.get("prompt_tokens", 0) or 0,
                              output_tokens=usage.get("completion_tokens", 0) or 0,
                              cost=usage.get("cost")),
        stop_reason=_stop_reason(choice.get("finish_reason")),
    )


def _stop_reason(reason: str | None) -> str | None:
    return "max_tokens" if reason == "length" else reason


def _affordable_tokens(response: httpx.Response, requested: int) -> int | None:
    try:
        error = response.json()["error"]
        message = error["message"]
        metadata = error.get("metadata") or {}
        if metadata.get("limit_source") == "openrouter_in_flight_budget" or not isinstance(message, str):
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    match = re.search(r"can only afford ([0-9]{1,9})\b", message, re.IGNORECASE)
    cap = int(match[1]) if match else 0
    return cap if 0 < cap < requested else None


@asynccontextmanager
async def _openai_response(role: Role, params: dict, *, stream: bool = False):
    route = routed(role)
    model = route or model_for(role)
    payload = _openai_payload(model, params, stream=stream, route=bool(route))
    # Respect custom writer choices. The default writer can use the main model on the
    # same configured route if its budget cannot cover a minimally useful response.
    alternate = (routed("main") if role == "write" and route and not get_settings().write_route
                 else None)
    budget = payload.get("max_tokens")
    min_tokens = 1024 if role == "write" else 512
    async with openai_client(bool(route)) as client:
        for attempt in range(3):
            async with client.stream("POST", "chat/completions", json=payload) as response:
                if not response.is_success:
                    await response.aread()
                if route and response.status_code == 402 and attempt < 2 and isinstance(budget, int):
                    cap = _affordable_tokens(response, payload["max_tokens"])
                    if cap and cap >= min_tokens:
                        payload["max_tokens"] = cap
                        continue
                    if cap and alternate and alternate != payload["model"]:
                        payload["model"] = alternate
                        payload["max_tokens"] = min(budget, 4000)
                        continue
                response.raise_for_status()
                yield response, payload["model"]
                return


async def _openai_create(role: Role, params: dict) -> Completion:
    async with _openai_response(role, params) as (response, model):
        await response.aread()
        result = _openai_completion(response.json())
        result.model = result.model or model
        return result


async def _openai_stream(role: Role, params: dict):
    text = []
    usage = CompletionUsage()
    finish_reason = None
    async with _openai_response(role, params, stream=True) as (r, response_model):
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            chunk = json.loads(raw)
            response_model = chunk.get("model") or response_model
            if chunk.get("usage"):
                u = chunk["usage"]
                usage = CompletionUsage(input_tokens=u.get("prompt_tokens", 0) or 0,
                                        output_tokens=u.get("completion_tokens", 0) or 0,
                                        cost=u.get("cost"))
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {}).get("content")
                if delta:
                    text.append(delta)
                    yield delta
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
    yield Completion([TextBlock("text", "".join(text))], response_model, usage,
                     _stop_reason(finish_reason))


@dataclass
class Usage:
    calls: list[dict] = field(default_factory=list)

    def record(self, model: str, usage: Any, purpose: str) -> None:
        self.calls.append({
            "purpose": purpose, "model": model,
            "input": getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0)) or 0,
            "output": getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0)) or 0,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "reported_cost": getattr(usage, "cost", None),
        })

    @property
    def cost_usd(self) -> float:
        total = 0.0
        settings = get_settings()
        for c in self.calls:
            if c.get("reported_cost") is not None:
                total += c["reported_cost"]
                continue
            if uses_openai_compatible(settings):
                total += (c["input"] * settings.openai_input_cost_per_million
                          + c["output"] * settings.openai_output_cost_per_million) / 1e6
                continue
            prompt_tokens = c["input"] + c["cache_read"] + c["cache_write"]
            table = LONG_PROMPT_PRICES if prompt_tokens > LONG_PROMPT_TOKENS else PRICES
            p_in, p_out, p_cache = table.get(c["model"], PRICES.get(c["model"], (0.0, 0.0, 0.0)))
            total += (c["input"] * p_in + c["cache_write"] * p_in * CACHE_WRITE_MULTIPLIER
                      + c["output"] * p_out + c["cache_read"] * p_cache) / 1e6
        return total

    def by_purpose(self) -> dict[str, dict]:
        """Tokens and cost per pipeline step, for cost breakdowns."""
        out: dict[str, dict] = {}
        for c in self.calls:
            row = out.setdefault(c["purpose"], {"calls": 0, "in": 0, "out": 0, "usd": 0.0})
            one = Usage([c])
            row["calls"] += 1
            row["in"] += c["input"] + c["cache_read"] + c["cache_write"]
            row["out"] += c["output"]
            row["usd"] = round(row["usd"] + one.cost_usd, 5)
        return out


    def summary(self) -> str:
        tokens_in = sum(c["input"] + c["cache_read"] + c["cache_write"] for c in self.calls)
        cached = sum(c["cache_read"] for c in self.calls)
        tokens_out = sum(c["output"] for c in self.calls)
        return (f"{len(self.calls)} calls, {tokens_in} in ({cached} from cache) / "
                f"{tokens_out} out tokens, ${self.cost_usd:.4f}")


def unavailable(exc: BaseException) -> bool:
    """The model provider refuses every call until someone acts: no credit left, a key that
    is wrong or revoked. Shown to the lawyer as such, not as a failed answer to retry."""
    status = getattr(exc, "status_code", None)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    return status in (401, 402, 403) or (status == 400 and "credit balance" in str(exc))


async def create(role: Role, usage: Usage, purpose: str, **params: Any):
    """messages.create with role-based model, refusal fallback, automatic prompt caching and
    usage recording. Caching matters in the tool loop, where every round resends the whole
    conversation including all fetched source texts."""
    model = routed(role) or model_for(role)
    if openai_for(role):
        response = await _openai_create(role, params)
        usage.record(response.model or model, response.usage, purpose)
        return response
    params.setdefault("cache_control", {"type": "ephemeral"})
    response = await client().beta.messages.create(
        model=model, betas=[FALLBACK_BETA], fallbacks="default", **params)
    usage.record(response.model or model, response.usage, purpose)
    return response


async def stream(role: Role, usage: Usage, purpose: str, **params: Any):
    """Streaming variant of `create`: yields text deltas (str), then the final message."""
    model = routed(role) or model_for(role)
    if openai_for(role):
        async for item in _openai_stream(role, params):
            if isinstance(item, str):
                yield item
            else:
                usage.record(item.model or model, item.usage, purpose)
                yield item
        return
    params.setdefault("cache_control", {"type": "ephemeral"})
    async with client().beta.messages.stream(
            model=model, betas=[FALLBACK_BETA], fallbacks="default", **params) as s:
        async for event in s:
            if event.type == "text":
                yield event.text
        final = await s.get_final_message()
    usage.record(final.model or model, final.usage, purpose)
    yield final

