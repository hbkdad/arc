"""Backup and restore.

Reference-repo-informed (fixed-scope archives, a closed SHA-256 manifest,
non-overwriting staged restore) but scoped to what ACR actually needs to
recover: `Settings.data_dir` -- the SQLite database and any
runtime-generated skills (`generated_skills/`) -- not the first-party
`skills/` package tree, which is already version-controlled in git and
isn't runtime state that could be lost.

`manifest.json` records a SHA-256 hash of every archived file.
`restore_backup()` verifies every hash BEFORE writing anything, checks
every archive member's path stays inside the target directory (zip-slip:
an archive member like `../../etc/passwd` must never be allowed to
extract outside `target_dir`), and refuses a non-empty target directory
unless the caller passes `force=True` -- a corrupted or malicious archive
should never silently overwrite good data.

Known limitation: this copies the SQLite file(s) directly rather than
using SQLite's own online-backup API, so a backup taken while something is
actively writing to the database could in principle capture an
inconsistent snapshot. Safe to run against an idle `acr` process; not yet
a hot-backup tool for a database under concurrent write load.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from acr import __version__

MANIFEST_NAME = "manifest.json"

__all__ = [
    "MANIFEST_NAME",
    "BackupIntegrityError",
    "BackupResult",
    "RestoreTargetNotEmptyError",
    "UnsafeArchiveMemberError",
    "create_backup",
    "restore_backup",
]


class BackupIntegrityError(RuntimeError):
    """Raised by `restore_backup()` when a file's content doesn't match
    the hash recorded in the archive's own manifest."""


class RestoreTargetNotEmptyError(RuntimeError):
    """Raised by `restore_backup()` when the target directory already has
    files and `force` wasn't passed."""


class UnsafeArchiveMemberError(RuntimeError):
    """Raised when an archive member's path would resolve outside the
    target directory (zip-slip) -- refused before any extraction."""


@dataclass(frozen=True, slots=True)
class BackupResult:
    archive_path: Path
    file_count: int
    total_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(data_dir: Path, archive_path: Path) -> BackupResult:
    """Snapshot every file under `data_dir` into a zip archive at
    `archive_path`, with a `manifest.json` listing each included file's
    relative path, byte size, and SHA-256 hash."""
    files = sorted(p for p in data_dir.rglob("*") if p.is_file())
    manifest: dict[str, Any] = {
        "acr_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "files": [],
    }
    total_bytes = 0
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.relative_to(data_dir).as_posix()
            size = path.stat().st_size
            total_bytes += size
            manifest["files"].append({"path": rel, "bytes": size, "sha256": _sha256_file(path)})
            zf.write(path, arcname=rel)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))

    return BackupResult(archive_path=archive_path, file_count=len(files), total_bytes=total_bytes)


def _safe_target(target_dir: Path, rel: str) -> Path:
    """Resolve `rel` against `target_dir`, refusing anything that would
    escape it."""
    candidate = (target_dir / rel).resolve()
    if not candidate.is_relative_to(target_dir.resolve()):
        raise UnsafeArchiveMemberError(rel)
    return candidate


def restore_backup(archive_path: Path, target_dir: Path, *, force: bool = False) -> int:
    """Verify every file's hash against `manifest.json` before writing
    anything. Refuses a non-empty `target_dir` unless `force=True`.
    Returns the number of files restored."""
    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        raise RestoreTargetNotEmptyError(str(target_dir))

    with zipfile.ZipFile(archive_path) as zf:
        manifest = json.loads(zf.read(MANIFEST_NAME))
        entries = manifest["files"]

        for entry in entries:
            dest = _safe_target(target_dir, entry["path"])  # raises before any write if unsafe
            data = zf.read(entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise BackupIntegrityError(entry["path"])

        target_dir.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            dest = _safe_target(target_dir, entry["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(entry["path"]))

    return len(entries)
