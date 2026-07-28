"""Context compiler and attribution (master §411-472)."""

from acr.context.attribution import AttributionResult, record_attribution
from acr.context.compiler import compile_context
from acr.context.models import ContextBundle, ContextItem, ContextSource

__all__ = [
    "AttributionResult",
    "ContextBundle",
    "ContextItem",
    "ContextSource",
    "compile_context",
    "record_attribution",
]
