from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, TypeVar

from .client import NeuroFenceClient


@dataclass(frozen=True)
class InterceptDecision:
    allowed: bool
    action: str
    reason: str
    score: float
    flagged: bool = False
    agent_isolated: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class SendFn(Protocol):
    def __call__(self, sender: str, recipient: Optional[str], content: str) -> Any: ...


T = TypeVar("T")


class NeuroFenceGuard:
    """Enforces NeuroFence decisions before messages are delivered.

    Usage:
        guard = NeuroFenceGuard(NeuroFenceClient("http://localhost:8000"))
        guarded_send = guard.wrap_send(send_fn)
        guarded_send("agent_a", "agent_b", "hello")

    The wrapped send function only gets called if NeuroFence returns allowed=True.
    """

    def __init__(
        self,
        client: Optional[NeuroFenceClient] = None,
        *,
        block_exception_type: type[Exception] = RuntimeError,
        block_flagged: bool = False,
        block_actions: Optional[set[str]] = None,
    ):
        self.client = client or NeuroFenceClient()
        self.block_exception_type = block_exception_type
        self.block_flagged = bool(block_flagged)
        self.block_actions = block_actions

    def intercept(self, sender: str, recipient: Optional[str], content: str) -> InterceptDecision:
        data = self.client.intercept(sender=sender, recipient=recipient, content=content)
        return InterceptDecision(
            allowed=bool(data.get("allowed")),
            action=str(data.get("action")),
            reason=str(data.get("reason")),
            score=float(data.get("score", 0.0)),
            flagged=bool(data.get("flagged", False)),
            agent_isolated=data.get("agent_isolated"),
            raw=data,
        )

    def enforce(self, sender: str, recipient: Optional[str], content: str) -> InterceptDecision:
        decision = self.intercept(sender, recipient, content)
        if not decision.allowed:
            raise self.block_exception_type(
                f"NeuroFence blocked message {sender} -> {recipient}: {decision.action} ({decision.reason})"
            )

        if self.block_actions and decision.action in self.block_actions:
            raise self.block_exception_type(
                f"NeuroFence policy blocked action {decision.action} for {sender} -> {recipient}: {decision.reason}"
            )

        if self.block_flagged and decision.flagged:
            raise self.block_exception_type(
                f"NeuroFence policy blocked flagged message {sender} -> {recipient}: {decision.action} ({decision.reason})"
            )
        return decision

    def wrap_send(self, send_fn: SendFn) -> SendFn:
        def wrapped(sender: str, recipient: Optional[str], content: str) -> Any:
            self.enforce(sender, recipient, content)
            return send_fn(sender, recipient, content)

        return wrapped


def wrap_send(
    send_fn: SendFn,
    *,
    base_url: str = "http://localhost:8000",
    timeout_seconds: float = 20.0,
    block_exception_type: type[Exception] = RuntimeError,
    block_flagged: bool = False,
    block_actions: Optional[set[str]] = None,
) -> SendFn:
    """Convenience wrapper to guard a send function without manual client creation."""

    guard = NeuroFenceGuard(
        NeuroFenceClient(base_url=base_url, timeout_seconds=timeout_seconds),
        block_exception_type=block_exception_type,
        block_flagged=block_flagged,
        block_actions=block_actions,
    )
    return guard.wrap_send(send_fn)
