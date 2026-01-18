"""Framework-agnostic SDK helpers for integrating NeuroFence.

This package is intentionally lightweight:
- Talks to the running NeuroFence API over HTTP.
- Provides wrappers/decorators to enforce interception on message send.
"""

from .client import NeuroFenceClient
from .guard import InterceptDecision, NeuroFenceGuard, wrap_send

__all__ = [
    "NeuroFenceClient",
    "InterceptDecision",
    "NeuroFenceGuard",
    "wrap_send",
]
