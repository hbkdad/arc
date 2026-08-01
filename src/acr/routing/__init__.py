"""Routing: model selection with escalation (master §794-825)."""

from acr.routing.factory import build_default_router
from acr.routing.models import (
    ModelProfile,
    ModelRouter,
    NoProviderAvailableError,
    RoutedCompletion,
)

__all__ = [
    "ModelProfile",
    "ModelRouter",
    "NoProviderAvailableError",
    "RoutedCompletion",
    "build_default_router",
]
