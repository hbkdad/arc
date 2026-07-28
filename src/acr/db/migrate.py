"""Programmatic Alembic migration runner — no `alembic.ini` required.

`uv run alembic upgrade head` (reading the repo's `alembic.ini`) is the
dev/source-checkout path; that file lives at the repo root, outside
`src/acr/`, so it never ships in the wheel. A `pip install acr` (or `uv
tool install acr`) user has no `alembic.ini` and no repo checkout at all
— just the installed package. `acr db upgrade` is that install's path:
build an equivalent `Config` pointing `script_location` at the migrations
Alembic's own build backend already bundles inside `acr.migrations`
(verified — see docs/ARCHITECTURE.md), then call Alembic's upgrade
command directly. Both paths execute the exact same `migrations/env.py`
(it resolves `Settings.database_url` itself either way), so behavior
never diverges between the dev and installed paths.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def build_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def upgrade_to_head() -> None:
    command.upgrade(build_config(), "head")
