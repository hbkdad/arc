"""Typed runtime settings for ACR (master spec principle #10 — local-first by default)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path.home() / ".acr"


class Settings(BaseSettings):
    """Local-first runtime configuration.

    Overridable via `ACR_*` environment variables or a `.env` file; never via
    committed source, so no secret ever needs to live in this repo.
    """

    model_config = SettingsConfigDict(env_prefix="ACR_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default_factory=_default_data_dir)
    log_level: str = "INFO"
    # "json" for machine-readable logs, "console" for human-readable dev output.
    log_format: str = "json"

    # Cloud providers are opt-in (master principle #2: cloud-optional). Unset
    # by default; ACR_OPENAI_API_KEY / ACR_ANTHROPIC_API_KEY enable them.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Ollama ships with no default model -- every install has pulled whatever
    # the user wanted. Unset means "auto-detect the first model `ollama list`
    # reports" (see acr.providers.ollama.OllamaProvider); set this to pin one.
    ollama_model: str | None = None

    # `acr run`/MCP `run_task` default to the zero-config mock provider
    # (tier 0) unless a caller explicitly raises --min-quality-tier. That
    # stays the safe *out-of-box* default -- a fresh install shouldn't
    # silently depend on a local daemon being up or start making paid API
    # calls. This setting is the persistent opt-in: set it once
    # (ACR_DEFAULT_MIN_QUALITY_TIER=1) and every `acr run`/MCP `run_task`
    # call that doesn't explicitly override the tier uses it from then on,
    # without needing --min-quality-tier on every invocation.
    default_min_quality_tier: int = 0

    # master §1534-1550: disables skill activation, destructive/reversible-
    # write tool invocation, and other mutating operations. Off by default.
    safe_mode: bool = False

    # master §1721-1727, Controlled Self-Improvement. self_improvement_enabled
    # is the master kill switch (on by default -- explicit user decision: ACR
    # should self-improve within the design/intent it was given). Proposals
    # always require explicit approval before taking effect unless
    # auto_apply_proposals is turned on (off by default -- also an explicit
    # user decision: approval-gated is the safe default, autonomous
    # application is an opt-in escape hatch, not the other way around).
    self_improvement_enabled: bool = True
    auto_apply_proposals: bool = False

    @property
    def database_path(self) -> Path:
        return self.data_dir / "acr.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached; env read once per process)."""
    return Settings()
