"""Security: permissions, trust, injection detection, secrets, sandbox,
safe mode, audit logs (master §1118-1224).

`acr.security.audit` is deliberately *not* re-exported here: it depends on
`acr.telemetry`, and `acr.telemetry.recorder` depends on
`acr.security.secrets` (to redact payloads before they're persisted/logged)
— aggregating audit's names into this package's eager imports would make
`acr.telemetry` -> `acr.security` (via secrets) -> `acr.security.audit` ->
`acr.telemetry` a real circular import. Import it directly:
`from acr.security.audit import record_audit_event`.
"""

from acr.security.injection import InjectionScanResult, scan_for_injection
from acr.security.permissions import Capability, PermissionDeniedError, PermissionSet
from acr.security.safe_mode import SafeModeError, require_not_safe_mode
from acr.security.sandbox import SandboxPolicy, build_sandboxed_env
from acr.security.secrets import contains_secret, redact_mapping, redact_secrets
from acr.security.trust import TrustLevel, combine_trust, memory_trust_level

__all__ = [
    "Capability",
    "InjectionScanResult",
    "PermissionDeniedError",
    "PermissionSet",
    "SafeModeError",
    "SandboxPolicy",
    "TrustLevel",
    "build_sandboxed_env",
    "combine_trust",
    "contains_secret",
    "memory_trust_level",
    "redact_mapping",
    "redact_secrets",
    "require_not_safe_mode",
    "scan_for_injection",
]
