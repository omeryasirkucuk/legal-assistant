"""Runtime configuration loaded from environment variables and the repo-level .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Product name is not decided yet; keep every user-visible mention behind this value.
    app_name: str = "Legal Assistant"

    # Signs session cookies. Override in .env for anything beyond local development.
    secret_key: str = "dev-only-insecure-secret"
    # Registration needs this code; empty means registration is closed.
    invite_code: str = ""
    # True behind HTTPS (the public deployment); False for plain-http local development.
    cookie_secure: bool = False
    # Per-user LLM spend allowed per calendar day (UTC), protecting the shared API key.
    daily_user_budget_usd: float = 3.0

    database_url: str = "postgresql+asyncpg://legal:legal@localhost:5433/legal"
    storage_dir: Path = REPO_ROOT / "var" / "storage"

    # LLM provider: Anthropic directly, or any OpenAI-compatible chat completions endpoint
    # (including Open WebUI). For Open WebUI, set OPENAI_BASE_URL to http://host:port/api.
    # Models are selected by role and must match the IDs exposed by the configured endpoint.
    # Every role defaults to the cheapest model on purpose: quality must come from the
    # system (planning, retrieval, review), not from an expensive model.
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "http://localhost:3000/api"
    openai_model_main: str = "gpt-4o-mini"
    openai_model_draft: str = "gpt-4o-mini"
    openai_model_cheap: str = "gpt-4o-mini"
    openai_model_judge: str = "gpt-4o-mini"
    # Optional provider-side rates; local Open WebUI models are usually zero-cost.
    openai_input_cost_per_million: float = 0.0
    openai_output_cost_per_million: float = 0.0
    model_main: str = "claude-haiku-5-5"     # answers and reasoning
    model_draft: str = "claude-haiku-5-5"    # petition drafting
    model_cheap: str = "claude-haiku-5-5"   # routing, claim-support checks, style rewrites
    model_judge: str = "claude-haiku-5-5"  # sentence-by-sentence review and completeness
    answer_effort: str = "low"              # effort for writing the answer
    plan_effort: str = "medium"             # effort for research planning (coverage)


@lru_cache
def get_settings() -> Settings:
    return Settings()
