"""Routing: model selection with escalation (master §794-825)."""

from acr.routing.models import (
    ModelProfile,
    ModelRouter,
    NoProviderAvailableError,
    RoutedCompletion,
    build_default_router,
)

__all__ = [
    "ModelProfile",
    "ModelRouter",
    "NoProviderAvailableError",
    "RoutedCompletion",
    "build_default_router",
]
