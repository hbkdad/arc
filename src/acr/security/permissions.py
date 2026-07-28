"""Capability permissions (master §1131-1149).

Default deny: a `PermissionSet` starts with nothing granted. Generated
skills may not grant themselves permissions (master §1148) — nothing in
this module lets a `Capability` grant itself; grants only ever come from
whoever constructs the `PermissionSet` (the CLI/caller acting on the
operator's behalf), never from skill or tool metadata itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    NETWORK_READ = "network.read"
    NETWORK_WRITE = "network.write"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    SHELL_EXECUTE = "shell.execute"
    DATABASE_READ = "database.read"
    DATABASE_WRITE = "database.write"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    SKILL_READ = "skill.read"
    SKILL_CREATE = "skill.create"
    SKILL_ACTIVATE = "skill.activate"
    AGENT_CREATE = "agent.create"
    CREDENTIAL_USE = "credential.use"
    DEPLOYMENT_EXECUTE = "deployment.execute"


class PermissionDeniedError(PermissionError):
    def __init__(self, capability: str) -> None:
        super().__init__(f"capability not granted: {capability}")
        self.capability = capability


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """An explicit, default-deny set of granted capabilities."""

    granted: frozenset[Capability] = field(default_factory=frozenset)

    def has(self, capability: Capability | str) -> bool:
        try:
            cap = Capability(capability)
        except ValueError:
            return False
        return cap in self.granted

    def require(self, *capabilities: Capability | str) -> None:
        for capability in capabilities:
            try:
                cap: Capability | str = Capability(capability)
            except ValueError:
                # An unrecognized capability string can never be granted —
                # default deny, not a crash (e.g. a tool/skill declaring a
                # permission the Capability enum doesn't know about yet).
                cap = capability
            if cap not in self.granted:
                raise PermissionDeniedError(str(cap))

    def require_all(self, capabilities: list[str]) -> None:
        self.require(*capabilities)


NONE_GRANTED = PermissionSet()
