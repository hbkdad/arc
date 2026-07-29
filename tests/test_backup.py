"""Tests for acr.backup."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from acr.backup import (
    MANIFEST_NAME,
    BackupIntegrityError,
    RestoreTargetNotEmptyError,
    UnsafeArchiveMemberError,
    create_backup,
    restore_backup,
)


def _seed_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "acr.db").write_bytes(b"fake sqlite content")
    generated = data_dir / "generated_skills" / "some-skill@v2"
    generated.mkdir(parents=True)
    (generated / "SKILL.yaml").write_text("id: some-skill@v2\n", encoding="utf-8")
    return data_dir


def test_create_backup_includes_every_file_with_a_real_hash(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"

    result = create_backup(data_dir, archive_path)

    assert result.file_count == 2
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as zf:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    paths = {f["path"] for f in manifest["files"]}
    assert paths == {"acr.db", "generated_skills/some-skill@v2/SKILL.yaml"}
    for entry in manifest["files"]:
        assert len(entry["sha256"]) == 64


def test_restore_backup_recreates_every_file(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)
    target_dir = tmp_path / "restored"

    count = restore_backup(archive_path, target_dir)

    assert count == 2
    assert (target_dir / "acr.db").read_bytes() == b"fake sqlite content"
    assert (target_dir / "generated_skills" / "some-skill@v2" / "SKILL.yaml").read_text(
        encoding="utf-8"
    ) == "id: some-skill@v2\n"


def test_restore_backup_refuses_a_non_empty_target_without_force(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)
    target_dir = tmp_path / "restored"
    target_dir.mkdir()
    (target_dir / "already-here.txt").write_text("don't overwrite me", encoding="utf-8")

    with pytest.raises(RestoreTargetNotEmptyError):
        restore_backup(archive_path, target_dir)

    assert (target_dir / "already-here.txt").exists()


def test_restore_backup_with_force_proceeds_into_a_non_empty_target(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)
    target_dir = tmp_path / "restored"
    target_dir.mkdir()
    (target_dir / "already-here.txt").write_text("stays put", encoding="utf-8")

    count = restore_backup(archive_path, target_dir, force=True)

    assert count == 2
    assert (target_dir / "acr.db").is_file()
    assert (target_dir / "already-here.txt").is_file()  # force doesn't wipe the dir, just proceeds


def test_restore_backup_rejects_a_tampered_file(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)

    # Tamper with acr.db's content in the archive after the manifest hash
    # was computed, simulating a corrupted or maliciously modified archive.
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive_path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "acr.db":
                data = b"corrupted content, wrong hash now"
            dst.writestr(name, data)

    with pytest.raises(BackupIntegrityError):
        restore_backup(tampered, tmp_path / "restored")


def test_restore_backup_rejects_a_zip_slip_path(tmp_path: Path) -> None:
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)

    # Build a malicious archive whose manifest claims a file path that
    # escapes the target directory.
    evil_path = "../../evil.txt"
    evil_content = b"i should never be written outside target_dir"
    evil = tmp_path / "evil.zip"
    manifest = {
        "acr_version": "0.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "files": [
            {
                "path": evil_path,
                "bytes": len(evil_content),
                "sha256": hashlib.sha256(evil_content).hexdigest(),
            }
        ],
    }
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr(evil_path, evil_content)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest))

    target_dir = tmp_path / "restore_target"
    with pytest.raises(UnsafeArchiveMemberError):
        restore_backup(evil, target_dir)


def test_restore_backup_rejects_an_absolute_path_manifest_entry(tmp_path: Path) -> None:
    # A different escape shape than "../": pathlib's `/` operator discards
    # the left operand entirely when the right operand looks like an
    # absolute path (Path("safe") / "C:/evil" == Path("C:/evil"), not
    # Path("safe/C:/evil")) -- a naive "join then check" implementation
    # could construct a candidate outside target_dir without ever
    # containing "..". _safe_target()'s is_relative_to() check happens
    # *after* the join for exactly this reason.
    data_dir = _seed_data_dir(tmp_path)
    archive_path = tmp_path / "backup.zip"
    create_backup(data_dir, archive_path)

    evil_path = str(tmp_path / "outside-target.txt")
    evil_content = b"absolute-path escape attempt"
    evil = tmp_path / "evil-absolute.zip"
    manifest = {
        "acr_version": "0.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "files": [
            {
                "path": evil_path,
                "bytes": len(evil_content),
                "sha256": hashlib.sha256(evil_content).hexdigest(),
            }
        ],
    }
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest))

    target_dir = tmp_path / "restore_target_2"
    # _safe_target() is checked before zf.read() in restore_backup(), so
    # this raises UnsafeArchiveMemberError even though the zip has no
    # member under that name -- the path itself is refused first.
    with pytest.raises(UnsafeArchiveMemberError):
        restore_backup(evil, target_dir)

    assert not (tmp_path / "outside-target.txt").exists()

    assert not (tmp_path / "evil.txt").exists()
