from __future__ import annotations

from pathlib import Path

from ..core.contracts import WorkerResult


def grounding_issues(result: WorkerResult, repo: Path) -> list[str]:
    issues: list[str] = []
    for item in result.evidence:
        evidence_path = Path(item.path)
        if not evidence_path.is_absolute():
            evidence_path = repo / evidence_path
        if not evidence_path.exists():
            issues.append(f"Evidence path does not exist: {item.path}")
    return issues
