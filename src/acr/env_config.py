"""Shared `.env` read/write helpers (master §37-41: secrets only ever in
`.env` / `Settings`, never DB, Git, or logs).

Both `acr setup` (CLI) and the dashboard's `/settings` page write provider
API keys the same way — one real implementation instead of two, so a
correctness fix in one path is a fix in both.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_ENV_PATH = Path(".env")
_ENV_EXAMPLE_PATH = Path(".env.example")

__all__ = ["DEFAULT_ENV_PATH", "ensure_env_file", "has_var", "set_var"]


def ensure_env_file(path: Path = DEFAULT_ENV_PATH) -> Path:
    """Create `path` (seeded from `.env.example` if present) if it doesn't exist yet."""
    if not path.exists():
        path.write_text(
            _ENV_EXAMPLE_PATH.read_text(encoding="utf-8") if _ENV_EXAMPLE_PATH.exists() else "",
            encoding="utf-8",
        )
    return path


def has_var(text: str, var: str) -> bool:
    """Whether `var=<non-empty>` is already assigned somewhere in `text`."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{var}=") and stripped[len(var) + 1 :]:
            return True
    return False


def set_var(path: Path, var: str, value: str) -> None:
    """Set `var=value` in the `.env` at `path` — replaces an existing
    assignment in place if one exists, otherwise appends a new one. Never
    logs or returns `value`."""
    ensure_env_file(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{var}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{var}={value}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n{var}={value}\n")
