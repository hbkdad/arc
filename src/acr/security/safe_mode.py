"""Safe mode (master §1534-1550).

Disables: skill activation, memory deletion, agent generation, shell
writes, autonomous optimization, destructive/reversible-write tools.
Permits: inspection, retrieval, read-only model use, diagnostics, exports.

Of that list, ACR currently has real, callable operations for skill
activation and tool invocation (side-effect level) — those are the two
places this is actually enforced today; the rest (memory deletion, agent
generation, autonomous optimization) don't exist yet as operations to
guard.
"""

from __future__ import annotations


class SafeModeError(PermissionError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"blocked by safe mode: {operation}")
        self.operation = operation


def require_not_safe_mode(safe_mode: bool, operation: str) -> None:
    if safe_mode:
        raise SafeModeError(operation)
