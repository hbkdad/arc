"""Tests for task lifecycle transition rules (master §959-967)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from acr.core.tasks.models import InvalidTransition, TaskStatus, validate_transition


def test_allows_created_to_planning() -> None:
    validate_transition(TaskStatus.CREATED, TaskStatus.PLANNING)


def test_allows_full_happy_path() -> None:
    path = [
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.EXECUTING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]
    for current, target in pairwise(path):
        validate_transition(current, target)


def test_rejects_created_to_completed() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(TaskStatus.CREATED, TaskStatus.COMPLETED)


@pytest.mark.parametrize(
    "terminal", [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
)
def test_terminal_statuses_have_no_outgoing_transitions(terminal: TaskStatus) -> None:
    for candidate in TaskStatus:
        with pytest.raises(InvalidTransition):
            validate_transition(terminal, candidate)
