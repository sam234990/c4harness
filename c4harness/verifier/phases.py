"""Proposal and post-integration verification phases.

Patch safety is checked before a proposal mutates the graph workspace.  File,
command and test checks run only after the proposal is integrated there.
"""

from __future__ import annotations

from pathlib import Path

from ..core.contracts import (
    FailureCategory,
    FailureRecord,
    VerificationResult,
    WorkerResult,
)
from ..core.graph import VerificationContract
from .executable import execute_checks
from .policy import policy_issues


PROPOSAL_CHECKS = frozenset(
    {"changed_paths_within_allowlist", "patch_non_empty", "requirement_coverage"}
)


def _name(expression: str) -> str:
    return expression.split(":", 1)[0]


def _contract_for_phase(
    contract: VerificationContract,
    *,
    proposal: bool,
) -> VerificationContract:
    checks = tuple(
        expression
        for expression in contract.deterministic_checks
        if (_name(expression) in PROPOSAL_CHECKS) is proposal
    )
    return VerificationContract(
        deterministic_checks=checks,
        evidence_requirements=() if proposal else contract.evidence_requirements,
        semantic_check=None if proposal else contract.semantic_check,
        root_contribution=contract.root_contribution,
    )


def _precheck(result: WorkerResult) -> VerificationResult | None:
    if result.status != "success":
        return VerificationResult(
            accepted=False,
            confidence="low",
            issues=[f"Worker execution status is {result.status!r}, not 'success'."],
            failures=[FailureRecord(
                category=FailureCategory.WORKER,
                code=f"worker:{result.status}",
                message=f"Worker execution status is {result.status!r}, not 'success'.",
                phase_or_check="precheck",
                retryable=True,
                blame="worker",
            )],
        )
    policy = policy_issues(result)
    if policy:
        policy_failures = [
            FailureRecord(
                category=FailureCategory.POLICY_PERMISSION,
                code="policy:violation",
                message=issue,
                phase_or_check="policy_precheck",
                retryable=False,
                blame="policy_permission",
            )
            for issue in policy
        ]
        return VerificationResult(False, "blocked", list(policy), failures=policy_failures)
    return None


def verify_patch_proposal(
    contract: VerificationContract,
    result: WorkerResult,
    repo: Path,
    *,
    timeout: int = 120,
    write_paths: tuple[str, ...] = (),
    requirement_refs: tuple[str, ...] = (),
    required_requirement_ids: tuple[str, ...] = (),
) -> VerificationResult:
    """Validate patch shape, allowlist and requirement coverage pre-integration."""
    early = _precheck(result)
    if early is not None:
        return early
    return execute_checks(
        _contract_for_phase(contract, proposal=True),
        result,
        repo,
        timeout=timeout,
        worker_output_path=result.raw_output_path,
        write_paths=write_paths,
        requirement_refs=requirement_refs,
        required_requirement_ids=required_requirement_ids,
    )


def verify_integrated_node(
    contract: VerificationContract,
    result: WorkerResult,
    repo: Path,
    *,
    timeout: int = 120,
    write_paths: tuple[str, ...] = (),
    requirement_refs: tuple[str, ...] = (),
    required_requirement_ids: tuple[str, ...] = (),
) -> VerificationResult:
    """Run artifact, command, test, evidence and semantic checks post-integration."""
    early = _precheck(result)
    if early is not None:
        return early
    return execute_checks(
        _contract_for_phase(contract, proposal=False),
        result,
        repo,
        timeout=timeout,
        worker_output_path=result.raw_output_path,
        write_paths=write_paths,
        requirement_refs=requirement_refs,
        required_requirement_ids=required_requirement_ids,
    )


def combine_phase_results(*results: VerificationResult) -> VerificationResult:
    """Merge results using blocked > rejected > inconclusive > accepted.

    Structured failures from all phases are preserved in the combined result.
    """
    if not results:
        return VerificationResult(True, "medium")
    issues = [issue for result in results for issue in result.issues]
    facts = [fact for result in results for fact in result.memory_facts]
    combined_failures = [
        failure for result in results for failure in result.failures
    ]
    if any(result.confidence == "blocked" for result in results):
        return VerificationResult(False, "blocked", issues, facts, combined_failures)
    if any(not result.accepted and result.confidence != "inconclusive" for result in results):
        return VerificationResult(False, "low", issues, facts, combined_failures)
    if any(not result.accepted or result.confidence == "inconclusive" for result in results):
        return VerificationResult(False, "inconclusive", issues, facts, combined_failures)
    confidence = "high" if all(result.confidence == "high" for result in results) else "medium"
    return VerificationResult(True, confidence, issues, facts, combined_failures)
