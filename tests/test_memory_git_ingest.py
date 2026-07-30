"""Tests for acr.memory.git_ingest -- automatic decision-memory capture
from real git commits (no manual step, see the module's own docstring)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from acr.config import Settings
from acr.memory.git_ingest import GitCommandError, read_commit, record_commit_as_decision
from acr.memory.write_controller import WriteDecision


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo_with_one_commit(tmp_path: Path, *, subject: str, body: str) -> Path:
    repo = tmp_path / "throwaway-repo"
    repo.mkdir()
    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=repo)
    _run(["git", "commit", "-m", f"{subject}\n\n{body}"], cwd=repo)
    return repo


def test_read_commit_returns_the_real_subject_and_body(tmp_path: Path) -> None:
    repo = _init_repo_with_one_commit(
        tmp_path, subject="Add the thing", body="Because it was needed for X."
    )

    commit = read_commit("HEAD", cwd=repo)

    assert len(commit.sha) == 40  # a real full git sha, not truncated
    assert commit.subject == "Add the thing"
    assert commit.body == "Because it was needed for X."


def test_read_commit_raises_for_an_unknown_revision(tmp_path: Path) -> None:
    repo = _init_repo_with_one_commit(tmp_path, subject="Add the thing", body="")

    with pytest.raises(GitCommandError):
        read_commit("not-a-real-revision", cwd=repo)


def test_read_commit_raises_outside_a_git_repository(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "just-a-directory"
    not_a_repo.mkdir()

    with pytest.raises(GitCommandError):
        read_commit("HEAD", cwd=not_a_repo)


async def test_record_commit_as_decision_stores_a_real_decision_memory(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    repo = _init_repo_with_one_commit(
        tmp_path,
        subject="Fix the flaky thing",
        body="Root cause was a race condition in the poller.",
    )

    evaluation, record = await record_commit_as_decision(db_session, "HEAD", cwd=repo)

    assert evaluation.decision in (WriteDecision.STORE_CANDIDATE, WriteDecision.STORE_CONFIRMED)
    assert record is not None
    assert "race condition" in record.content
    assert record.subject.startswith("acr.git.commit.")


async def test_record_commit_as_decision_is_idempotent_for_the_same_commit(
    migrated_settings: Settings, db_session: AsyncSession, tmp_path: Path
) -> None:
    repo = _init_repo_with_one_commit(
        tmp_path, subject="Add the thing", body="Because it was needed."
    )

    first, _ = await record_commit_as_decision(db_session, "HEAD", cwd=repo)
    await db_session.flush()
    second, _ = await record_commit_as_decision(db_session, "HEAD", cwd=repo)

    assert first.decision in (WriteDecision.STORE_CANDIDATE, WriteDecision.STORE_CONFIRMED)
    assert second.decision == WriteDecision.IGNORE
    assert "duplicate" in second.reason
