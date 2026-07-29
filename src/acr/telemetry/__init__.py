"""Telemetry: structured, secret-free event recording (master §32, §992-1024)."""

from acr.telemetry.explain import TaskExplanation, TaskNotFoundError, explain_task
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder

__all__ = [
    "TaskExplanation",
    "TaskNotFoundError",
    "TelemetryEvent",
    "TelemetryRecorder",
    "explain_task",
]
