"""Automatic decision-memory capture from this repo's own git history.

A self-evolving system shouldn't depend on a human (or an AI assistant
acting as one) remembering to hand-write a memory record after the fact
-- every real commit to this repo already carries its own rationale in
its own message (this project's own commit convention is a real
subject/body, not a one-liner), so this turns that into a genuine
`MemoryType.DECISION` record with zero manual step, via a git
`post-commit` hook (`.githooks/post-commit`) rather than a script someone
has to remember to run.

`remember_decision()`'s own duplicate detection (same type/scope/subject
with identical content -> `WriteDecision.IGNORE`) makes this naturally
idempotent: recording the same commit twice (a hook re-run, a manual
`acr memory record-commit <sha>` after the hook already fired) is a
no-op, not a duplicate entry.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from acr.memory.models import MemoryRecord, MemoryScope
from acr.memory.schemas import DecisionPayload
from acr.memory.write_controller import WriteEvaluation, remember_decision

# Unit separator (0x1F) -- a real character no commit message is
# realistically going to contain, unlike "|" or ":" which commit
# messages use constantly.
_FIELD_SEP = "\x1f"

__all__ = ["CommitInfo", "GitCommandError", "read_commit", "record_commit_as_decision"]


class GitCommandError(RuntimeError):
    """Raised when `git log` fails -- not a git repo, an unknown revision,
    or `git` itself isn't on PATH."""


@dataclass(frozen=True, slots=True)
class CommitInfo:
    sha: str
    subject: str
    body: str


def read_commit(rev: str = "HEAD", *, cwd: Path | None = None) -> CommitInfo:
    """Real `git log` output for `rev` -- never fabricated, and this
    raises rather than guessing if git itself fails."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", f"--format=%H{_FIELD_SEP}%s{_FIELD_SEP}%b", rev],
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise GitCommandError("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GitCommandError(f"git log failed for revision {rev!r}: {exc.stderr.strip()}") from exc

    sha, _, rest = result.stdout.partition(_FIELD_SEP)
    subject, _, body = rest.partition(_FIELD_SEP)
    return CommitInfo(sha=sha.strip(), subject=subject.strip(), body=body.strip())


async def record_commit_as_decision(
    session: AsyncSession, rev: str = "HEAD", *, cwd: Path | None = None
) -> tuple[WriteEvaluation, MemoryRecord | None]:
    """Read `rev`'s real commit message and store it as a `DECISION`
    memory. `subject` is keyed on the commit's own full sha, so re-running
    this for the same commit is a real no-op (see module docstring), not a
    duplicate."""
    commit = read_commit(rev, cwd=cwd)
    payload = DecisionPayload(
        context=commit.subject,
        rationale=commit.body or commit.subject,
    )
    return await remember_decision(
        session,
        payload,
        subject=f"acr.git.commit.{commit.sha}",
        scope=MemoryScope.PROJECT,
        source_type="git_commit",
        confidence=0.8,
        evidence=f"git commit {commit.sha}",
    )
