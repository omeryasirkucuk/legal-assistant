"""Loads LLM instructions from the repo-level prompts/tr directory by name."""

from __future__ import annotations

from functools import cache

from legal_api.config import REPO_ROOT

PROMPT_DIR = REPO_ROOT / "prompts" / "tr"


@cache
def prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
