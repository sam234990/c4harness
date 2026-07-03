"""Built-in lifecycle event mechanism."""

from __future__ import annotations

from ..core.contracts import RouteDecision, Task, VerificationResult, WorkerResult


class HookSet:
    """Internal hook placeholders.

    First implementation keeps hooks as no-ops so the call sites are explicit
    without introducing a plugin system yet.
    """

    def pre_ground(self, task: Task) -> None:
        return None

    def post_ground(self, task: Task, situation: object) -> None:
        return None

    def pre_decompose(self, situation: object) -> None:
        return None

    def post_decompose(self, situation: object, plan: object) -> None:
        return None

    def pre_route(self, task: Task) -> None:
        return None

    def post_route(self, task: Task, decision: RouteDecision) -> None:
        return None

    def pre_delegate(self, task: Task, decision: RouteDecision) -> None:
        return None

    def post_delegate(self, task: Task, result: WorkerResult) -> None:
        return None

    def post_verify(self, task: Task, verification: VerificationResult) -> None:
        return None

    def on_replan(self, plan: object, reason: str) -> None:
        return None

    def post_root_verify(self, plan: object, verification: VerificationResult) -> None:
        return None


__all__ = ["HookSet"]
