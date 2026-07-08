"""Evidence-based failure attribution for execution-history outcomes.

Classifies each completed node execution into an ExecutionOutcome with a
deterministic FailureAttribution. Uses explicit evidence (exception types,
structured result fields, verifier check names) rather than broad substring
guessing wherever possible.

Attributions in ``_EXCLUDED_ATTRIBUTIONS`` (from history/profiles.py) are
deliberately excluded from negative worker capability evidence: environment,
permission, consent, missing-context, assignment, and decomposition failures
must not penalize a worker's capability profile.
"""

from __future__ import annotations

from ..core.contracts import VerificationResult, WorkerResult
from ..history.contracts import ExecutionOutcome, FailureAttribution, OutcomeStatus


def _classify_exception(error: Exception) -> tuple[OutcomeStatus, FailureAttribution]:
    """Classify an exception into status and attribution using explicit type evidence.

    Exception hierarchy is used as structured evidence:
    - ``PermissionError`` → permission block
    - ``FileNotFoundError`` / ``NotADirectoryError`` → missing context
    - ``OSError`` / ``ConnectionError`` / ``TimeoutError`` → environment failure
    - Everything else → worker error
    """
    if isinstance(error, PermissionError):
        return OutcomeStatus.BLOCKED, FailureAttribution.PERMISSION_BLOCKED
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return OutcomeStatus.BLOCKED, FailureAttribution.MISSING_CONTEXT
    if isinstance(error, (OSError, ConnectionError, TimeoutError)):
        return OutcomeStatus.BLOCKED, FailureAttribution.ENVIRONMENT_FAILURE
    return OutcomeStatus.FAILED, FailureAttribution.WORKER_ERROR


def _classify_block_reasons(issues: list[str]) -> FailureAttribution:
    """Classify blocked verification into a specific attribution.

    Prefers explicit verifier-check-name evidence when present, then falls
    back to targeted keyword matching.  All returned values are members of
    ``_EXCLUDED_ATTRIBUTIONS`` so they never penalize worker capability.
    """
    for issue in issues:
        lower = issue.lower()
        # Explicit verifier check names (highest-confidence evidence).
        if "changed_paths_within_allowlist" in lower:
            return FailureAttribution.PERMISSION_BLOCKED
        if "file_exists" in lower:
            return FailureAttribution.MISSING_CONTEXT
        if "command_exit_zero" in lower and ("timeout" in lower or "timed out" in lower):
            return FailureAttribution.ENVIRONMENT_FAILURE
        # Consent scope (explicit signal from consent-aware checks).
        if "consent" in lower:
            return FailureAttribution.CONSENT_SCOPE_CHANGED
        # Targeted keyword fallbacks.
        if any(kw in lower for kw in ("permission", "policy", "allowlist")):
            return FailureAttribution.PERMISSION_BLOCKED
        if any(kw in lower for kw in ("not found", "missing")):
            return FailureAttribution.MISSING_CONTEXT
        if any(kw in lower for kw in ("timeout", "environment", "connection")):
            return FailureAttribution.ENVIRONMENT_FAILURE
    # Default: treat unknown blocks as environment failures (safe for profiles).
    return FailureAttribution.ENVIRONMENT_FAILURE


def attribute_outcome(
    *,
    task_id: str,
    node_id: str,
    worker_arm_id: str | None,
    result: WorkerResult | None,
    verification: VerificationResult | None,
    exception: Exception | None = None,
    capability_dimensions: tuple[str, ...] = (),
    artifact_refs: tuple[str, ...] = (),
    latency_ms: int | None = None,
) -> ExecutionOutcome:
    """Build a deterministic ``ExecutionOutcome`` from execution evidence.

    Attribution priority (highest first):

    1. Runner exception — classified by exception type.
    2. Policy violations in ``WorkerResult`` — explicit structured field.
    3. Verification result — accepted / inconclusive / blocked / rejected.
    4. Worker self-reported status (no verifier available).

    Token usage is extracted from ``WorkerResult.token_usage`` when present.
    Artifact refs default to ``result.changed_paths`` when the caller does
    not supply explicit refs.
    """
    # --- 1. Exception during worker execution ---
    if exception is not None:
        status, attribution = _classify_exception(exception)
        return _build_outcome(
            task_id=task_id,
            node_id=node_id,
            worker_arm_id=worker_arm_id,
            status=status,
            attribution=attribution,
            result=result,
            capability_dimensions=capability_dimensions,
            artifact_refs=artifact_refs,
            latency_ms=latency_ms,
            verification_status=None,
        )

    # --- 2. No result (defensive; shouldn't happen when executed) ---
    if result is None:
        return _build_outcome(
            task_id=task_id,
            node_id=node_id,
            worker_arm_id=worker_arm_id,
            status=OutcomeStatus.INCONCLUSIVE,
            attribution=FailureAttribution.WORKER_ERROR,
            result=None,
            capability_dimensions=capability_dimensions,
            artifact_refs=artifact_refs,
            latency_ms=latency_ms,
            verification_status=None,
        )

    # --- 3. Explicit policy violations in worker result ---
    if result.policy_violations:
        return _build_outcome(
            task_id=task_id,
            node_id=node_id,
            worker_arm_id=worker_arm_id,
            status=OutcomeStatus.BLOCKED,
            attribution=FailureAttribution.PERMISSION_BLOCKED,
            result=result,
            capability_dimensions=capability_dimensions,
            artifact_refs=artifact_refs,
            latency_ms=latency_ms,
            verification_status=None,
        )

    # A worker execution that did not report success cannot be promoted by
    # a verifier that only happened to observe valid surrounding artifacts.
    if result.status != "success":
        return _build_outcome(
            task_id=task_id,
            node_id=node_id,
            worker_arm_id=worker_arm_id,
            status=OutcomeStatus.FAILED,
            attribution=FailureAttribution.WORKER_ERROR,
            result=result,
            capability_dimensions=capability_dimensions,
            artifact_refs=artifact_refs,
            latency_ms=latency_ms,
            verification_status=(verification.confidence if verification else None),
        )

    # --- 4. Verification result ---
    verification_status: str | None = None
    if verification is not None:
        verification_status = verification.confidence
        if verification.accepted:
            status = OutcomeStatus.SUCCESS
            attribution = FailureAttribution.NONE
        elif verification.confidence == "inconclusive":
            status = OutcomeStatus.INCONCLUSIVE
            attribution = FailureAttribution.VERIFICATION_INCONCLUSIVE
        elif verification.confidence == "blocked":
            status = OutcomeStatus.BLOCKED
            attribution = _classify_block_reasons(verification.issues)
        else:
            status = OutcomeStatus.FAILED
            attribution = FailureAttribution.WORKER_ERROR
    else:
        # No verifier available — trust worker self-report.
        if result.status == "success":
            status = OutcomeStatus.SUCCESS
            attribution = FailureAttribution.NONE
        else:
            status = OutcomeStatus.FAILED
            attribution = FailureAttribution.WORKER_ERROR

    return _build_outcome(
        task_id=task_id,
        node_id=node_id,
        worker_arm_id=worker_arm_id,
        status=status,
        attribution=attribution,
        result=result,
        capability_dimensions=capability_dimensions,
        artifact_refs=artifact_refs,
        latency_ms=latency_ms,
        verification_status=verification_status,
    )


def _build_outcome(
    *,
    task_id: str,
    node_id: str,
    worker_arm_id: str | None,
    status: OutcomeStatus,
    attribution: FailureAttribution,
    result: WorkerResult | None,
    capability_dimensions: tuple[str, ...],
    artifact_refs: tuple[str, ...],
    latency_ms: int | None,
    verification_status: str | None,
) -> ExecutionOutcome:
    """Assemble an ``ExecutionOutcome``, extracting token usage from result."""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    if result is not None and result.token_usage:
        input_tokens = result.token_usage.input_tokens
        output_tokens = result.token_usage.output_tokens
        total_tokens = result.token_usage.total_tokens

    # Fall back to worker changed_paths when caller didn't supply refs.
    effective_refs = artifact_refs
    if not effective_refs and result is not None and result.changed_paths:
        effective_refs = tuple(result.changed_paths)

    return ExecutionOutcome(
        task_id=task_id,
        node_id=node_id,
        worker_arm_id=worker_arm_id,
        status=status,
        capability_dimensions=capability_dimensions,
        verification_status=verification_status,
        failure_attribution=attribution,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        artifact_refs=effective_refs,
    )
