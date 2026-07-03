from __future__ import annotations

from ..core.contracts import Task, TaskMode, WorkerResult


def structural_issues(result: WorkerResult, task: Task | None = None) -> list[str]:
    issues: list[str] = []
    if not result.summary.strip():
        issues.append("Worker result is missing summary.")
    if not result.evidence:
        issues.append("Worker result has no evidence.")
    if not result.next_steps:
        issues.append("Worker result has no next steps.")

    if task and task.constraints.mode == TaskMode.PATCH:
        if not result.changed_paths:
            issues.append("Patch task produced no changed paths.")
        if not result.proposed_patch_path:
            issues.append("Patch task produced no patch proposal.")
        elif not result.proposed_patch_path.exists():
            issues.append(f"Patch proposal does not exist: {result.proposed_patch_path}")
    return issues
