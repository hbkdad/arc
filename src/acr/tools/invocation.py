"""Authorized tool invocation (master §826-845 + §1131-1149 + §1534-1550).

The single real seam where a tool's declared `permissions` and
`side_effect_level` actually get enforced, instead of being descriptive
metadata nobody checks. Every call — granted or denied — is audit-logged
(master §1178-1179).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from acr.security.audit import record_audit_event
from acr.security.permissions import PermissionDeniedError, PermissionSet
from acr.security.safe_mode import SafeModeError, require_not_safe_mode
from acr.telemetry.recorder import TelemetryRecorder
from acr.tools.models import SideEffectLevel, ToolSpec
from acr.tools.registry import ToolRegistry

# side-effect levels safe mode blocks (master §1543: "destructive tools";
# a reversible write is still a mutation safe mode should not perform).
_BLOCKED_IN_SAFE_MODE = frozenset({SideEffectLevel.REVERSIBLE_WRITE, SideEffectLevel.DESTRUCTIVE})


async def invoke_tool(
    session: AsyncSession,
    registry: ToolRegistry,
    name: str,
    *,
    grants: PermissionSet,
    telemetry: TelemetryRecorder,
    safe_mode: bool = False,
    task_id: str | None = None,
    **kwargs: Any,
) -> Any:
    """Look up `name`, authorize it, then call its handler with `session` and `kwargs`.

    Raises `PermissionDeniedError` if `grants` doesn't cover every
    permission the tool declares, or `SafeModeError` if `safe_mode` is set
    and the tool isn't read-only. Both are audit-logged before raising.
    """
    tool: ToolSpec = registry.get(name)

    try:
        if tool.side_effect_level in _BLOCKED_IN_SAFE_MODE:
            require_not_safe_mode(safe_mode, f"tool.invoke:{name}")
        grants.require_all(tool.permissions)
    except (SafeModeError, PermissionDeniedError) as exc:
        await record_audit_event(
            session,
            telemetry,
            action=f"tool.invoke:{name}",
            outcome="denied",
            detail={"reason": str(exc)},
            task_id=task_id,
        )
        raise

    result = await tool.handler(session, **kwargs)
    await record_audit_event(
        session, telemetry, action=f"tool.invoke:{name}", outcome="granted", task_id=task_id
    )
    return result
