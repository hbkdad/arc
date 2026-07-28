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

    # master §1534-1550: disables skill activation, destructive/reversible-
    # write tool invocation, and other mutating operations. Off by default.
    safe_mode: bool = False

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
