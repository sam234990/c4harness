from __future__ import annotations

from pathlib import Path

from ..core.contracts import Task, VerificationResult, WorkerResult
from .grounding import grounding_issues
from .policy import policy_issues
from .structural import structural_issues


def verify_worker_result(
    result: WorkerResult,
    repo: Path,
    task: Task | None = None,
) -> VerificationResult:
    issues = structural_issues(result, task)
    issues.extend(policy_issues(result))
    issues.extend(grounding_issues(result, repo))
    facts: list[str] = []

    if not issues and result.summary.strip() and result.evidence:
        facts.append(result.summary.strip())

    return VerificationResult(
        accepted=not issues,
        confidence="medium" if not issues else "low",
        issues=issues,
        memory_facts=facts,
    )
