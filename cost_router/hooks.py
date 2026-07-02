from __future__ import annotations

from .schemas import RouteDecision, Task, VerificationResult, WorkerResult


class HookSet:
    """Internal hook placeholders.

    First implementation keeps hooks as no-ops so the call sites are explicit
    without introducing a plugin system yet.
    """

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
