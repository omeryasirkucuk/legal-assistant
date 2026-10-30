"""Client for a decision model: typed questions answered with probabilities, no generated text.

Used where a judgment can be read off a given text (does this article answer this question?).
Such a model is cheap, fast and gives nearly the same probabilities on every run, which keeps
the answer structure stable. Served through OpenRouter's Decisions API.
"""

from __future__ import annotations

import httpx

from legal_api import llm
from legal_api.config import get_settings


def enabled() -> bool:
    return bool(get_settings().decision_api_key)


async def yes_probabilities(client: httpx.AsyncClient, state: dict,
                            questions: dict[str, str], usage: llm.Usage,
                            purpose: str) -> dict[str, float | None]:
    """P(yes) for each yes/no question (name -> instructions) about `state`, in one request;
    None for a question the service did not answer."""
    s = get_settings()
    body = {"model": s.decision_model, "state": state,
            "questions": {name: {"type": "noul", "instructions": text}
                          for name, text in questions.items()}}
    try:
        response = await client.post("alpha/decisions", json=body)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return dict.fromkeys(questions)
    _record(data, usage, purpose)
    answers = data.get("answers") or {}
    out: dict[str, float | None] = {}
    for name in questions:
        value = (answers.get(name) or {}).get("noul")
        out[name] = float(value) if isinstance(value, int | float) else None
    return out


async def choose(client: httpx.AsyncClient, state: dict, instructions: str,
                 criteria: dict[str, str], usage: llm.Usage, purpose: str
                 ) -> tuple[str, float] | None:
    """The most likely option (name -> description) and its probability; None on failure."""
    s = get_settings()
    body = {"model": s.decision_model, "state": state,
            "questions": {"q": {"type": "choice", "instructions": instructions,
                                "criteria": criteria}}}
    try:
        response = await client.post("alpha/decisions", json=body)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    _record(data, usage, purpose)
    answer = (data.get("answers") or {}).get("q") or {}
    probabilities = answer.get("probabilities") or {}
    choice = answer.get("choice")
    if choice not in criteria:
        return None
    return choice, float(probabilities.get(choice, 0.0))


def _record(data: dict, usage: llm.Usage, purpose: str) -> None:
    s = get_settings()
    cost = (data.get("usage") or {}).get("cost")
    usage.record(s.decision_model, llm.CompletionUsage(
        input_tokens=(data.get("usage") or {}).get("prompt_tokens", 0) or 0,
        cost=float(cost) if cost is not None else None), purpose)


def client() -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(base_url=s.decision_base_url.rstrip("/") + "/",
                             headers={"authorization": f"Bearer {s.decision_api_key}",
                                      "content-type": "application/json"},
                             timeout=httpx.Timeout(30.0, connect=10.0))
