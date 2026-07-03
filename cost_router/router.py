from __future__ import annotations

from pathlib import Path

from .config.providers import ProviderConfig
from .core.contracts import Difficulty, Risk, RouteDecision, Task, TaskMode


LOG_SUFFIXES = {".log", ".out", ".err", ".txt"}


def route_task(task: Task, provider: ProviderConfig, worker: str) -> RouteDecision:
    if task.constraints.mode != TaskMode.READ_ONLY:
        return RouteDecision(
            difficulty=Difficulty.HARD,
            risk=Risk.PATCH,
            can_delegate=False,
            backend="main_agent",
            worker="main",
            model="strong",
            reason="Codex subagent backend currently delegates read-only tasks only.",
        )

    if _looks_like_log_task(task):
        return RouteDecision(
            difficulty=Difficulty.SIMPLE,
            risk=Risk.READ_ONLY,
            can_delegate=True,
            backend="codex_subagent",
            worker=worker,
            model=provider.model,
            reason="Read-only log analysis is low-risk and evidence-based.",
        )

    return RouteDecision(
        difficulty=Difficulty.MEDIUM,
        risk=Risk.READ_ONLY,
        can_delegate=True,
        backend="codex_subagent",
        worker=worker,
        model=provider.model,
        reason="Read-only exploration can be delegated to a low-cost subagent.",
    )


def _looks_like_log_task(task: Task) -> bool:
    goal = task.goal.lower()
    if any(word in goal for word in ("log", "failure", "error", "traceback", "oom")):
        return True
    return any(_has_log_suffix(path) for path in task.paths)


def _has_log_suffix(path: Path) -> bool:
    return path.suffix.lower() in LOG_SUFFIXES
