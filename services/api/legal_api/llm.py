"""Anthropic client, per-role model selection and token/cost accounting.

Every call goes through `create()` so usage is always recorded. Requests opt into the
server-side refusal fallback ("default" mode), so a safety decline on the main model is
retried on the server-chosen substitute instead of failing the user's request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import Any, Literal

import anthropic

from legal_api.config import get_settings

Role = Literal["main", "draft", "cheap", "judge"]
FALLBACK_BETA = "server-side-fallback-2026-07-01"

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


def model_for(role: Role) -> str:
    s = get_settings()
    return {"main": s.model_main, "draft": s.model_draft, "cheap": s.model_cheap,
            "judge": s.model_judge}[role]


@cache
def client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    if settings.llm_provider != "anthropic":
        raise NotImplementedError(f"provider {settings.llm_provider!r} is not wired yet")
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)


@dataclass
class Usage:
    calls: list[dict] = field(default_factory=list)

    def record(self, model: str, usage: Any, purpose: str) -> None:
        self.calls.append({
            "purpose": purpose, "model": model,
            "input": usage.input_tokens, "output": usage.output_tokens,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        })

    @property
    def cost_usd(self) -> float:
        total = 0.0
        for c in self.calls:
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


async def create(role: Role, usage: Usage, purpose: str, **params: Any):
    """messages.create with role-based model, refusal fallback, automatic prompt caching and
    usage recording. Caching matters in the tool loop, where every round resends the whole
    conversation including all fetched source texts."""
    model = model_for(role)
    params.setdefault("cache_control", {"type": "ephemeral"})
    response = await client().beta.messages.create(
        model=model, betas=[FALLBACK_BETA], fallbacks="default", **params)
    usage.record(response.model or model, response.usage, purpose)
    return response


async def stream(role: Role, usage: Usage, purpose: str, **params: Any):
    """Streaming variant of `create`: yields text deltas (str), then the final message."""
    model = model_for(role)
    params.setdefault("cache_control", {"type": "ephemeral"})
    async with client().beta.messages.stream(
            model=model, betas=[FALLBACK_BETA], fallbacks="default", **params) as s:
        async for event in s:
            if event.type == "text":
                yield event.text
        final = await s.get_final_message()
    usage.record(final.model or model, final.usage, purpose)
    yield final

