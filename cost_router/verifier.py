from __future__ import annotations

from pathlib import Path

from .schemas import Task, TaskMode, VerificationResult, WorkerResult


def verify_worker_result(
    result: WorkerResult,
    repo: Path,
    task: Task | None = None,
) -> VerificationResult:
    issues: list[str] = []
    facts: list[str] = []

    if not result.summary.strip():
        issues.append("Worker result is missing summary.")
    if not result.evidence:
        issues.append("Worker result has no evidence.")
    if not result.next_steps:
        issues.append("Worker result has no next steps.")
    issues.extend(result.policy_violations)

    if task and task.constraints.mode == TaskMode.PATCH:
        if not result.changed_paths:
            issues.append("Patch task produced no changed paths.")
        if not result.proposed_patch_path:
            issues.append("Patch task produced no patch proposal.")
        elif not result.proposed_patch_path.exists():
            issues.append(f"Patch proposal does not exist: {result.proposed_patch_path}")

    for item in result.evidence:
        evidence_path = Path(item.path)
        if not evidence_path.is_absolute():
            evidence_path = repo / evidence_path
        if not evidence_path.exists():
            issues.append(f"Evidence path does not exist: {item.path}")

    if not issues and result.summary.strip() and result.evidence:
        facts.append(result.summary.strip())

    return VerificationResult(
        accepted=not issues,
        confidence="medium" if not issues else "low",
        issues=issues,
        memory_facts=facts,
    )
