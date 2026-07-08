from __future__ import annotations

from pathlib import Path

from ..core.contracts import (
    Task,
    VerificationResult,
    WorkerResult,
)
from ..core.graph import TaskNodeContract
from .executable import execute_checks
from .grounding import grounding_issues
from .policy import policy_issues
from .structural import structural_issues


def verify_worker_result(
    result: WorkerResult,
    repo: Path,
    task: Task | None = None,
) -> VerificationResult:
    """Legacy verification entry point.

    Performs structural, policy, and grounding checks on a ``WorkerResult``.
    Preserved for backward compatibility with callers that do not use the
    contract-aware verification path.

    Returns a :class:`VerificationResult` with ``accepted``, ``confidence``,
    ``issues``, and ``memory_facts``.
    """
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


def verify_node(
    contract: TaskNodeContract,
    result: WorkerResult,
    repo: Path,
    *,
    timeout: int = 120,
    required_requirement_ids: tuple[str, ...] | None = None,
) -> VerificationResult:
    """Contract-aware node verification entry point.

    Consumes ``TaskNodeContract.verification`` plus ``WorkerResult`` and
    repository context.  Executes compiled deterministic checks safely and
    returns the existing :class:`VerificationResult` with explicit
    accepted/rejected/inconclusive/blocked semantics encoded consistently in
    ``accepted``, ``confidence``, and ``issues``.

    Design guarantees:
    - Deterministic failures cannot be overridden by semantic criteria.
    - Evidence requirements and semantic checks that cannot be proven locally
      yield *inconclusive* rather than false acceptance.
    - Patch checks validate the proposed patch and changed-path allowlist
      against ``contract.write_paths``.
    - Every path is resolved under ``repo``; traversal and symlink escape are
      blocked.
    - Subprocess timeout and captured output are bounded.
    - No command execution occurs when an earlier policy check blocks.

    Args:
        contract: The task node contract containing verification design.
        result: The worker result to verify.
        repo: The repository root for path resolution.
        timeout: Maximum subprocess timeout in seconds (bounded to 120s).

    Returns:
        A :class:`VerificationResult` encoding the verification outcome.
    """
    verification = contract.verification

    if result.status != "success":
        return VerificationResult(
            accepted=False,
            confidence="low",
            issues=[f"Worker execution status is {result.status!r}, not 'success'."],
        )
    policy = policy_issues(result)
    if policy:
        return VerificationResult(
            accepted=False,
            confidence="blocked",
            issues=policy,
        )

    # Resolve write_paths from contract (Path objects -> strings).
    write_paths = tuple(str(wp) for wp in contract.write_paths)

    # Resolve requirement information.
    requirement_refs = contract.requirement_refs
    # required_requirement_ids must be provided externally; for now we use
    # the requirement_refs from the contract as the coverage baseline.
    # The caller (Application layer) is responsible for passing the full
    # RequirementLedger when available.
    required_ids = (
        contract.requirement_refs
        if required_requirement_ids is None
        else required_requirement_ids
    )

    return execute_checks(
        verification,
        result,
        repo,
        timeout=timeout,
        worker_output_path=result.raw_output_path,
        write_paths=write_paths,
        requirement_refs=requirement_refs,
        required_requirement_ids=required_ids,
    )
