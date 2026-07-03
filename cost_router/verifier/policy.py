from __future__ import annotations

from ..core.contracts import WorkerResult


def policy_issues(result: WorkerResult) -> list[str]:
    return list(result.policy_violations)
