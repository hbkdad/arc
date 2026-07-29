"""Telemetry: structured, secret-free event recording (master §32, §992-1024)."""

from acr.telemetry.explain import TaskExplanation, TaskNotFoundError, explain_task
from acr.telemetry.models import TelemetryEvent
from acr.telemetry.recorder import TelemetryRecorder
from acr.telemetry.usage import ProviderUsage, usage_by_provider

__all__ = [
    "ProviderUsage",
    "TaskExplanation",
    "TaskNotFoundError",
    "TelemetryEvent",
    "TelemetryRecorder",
    "explain_task",
    "usage_by_provider",
]
