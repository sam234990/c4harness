from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.contracts import FailureCategory, VerificationResult
    from ..core.graph import TaskNodeContract


class ReplanReason(str, Enum):
    MISSING_CONTEXT = "missing_context"
    WORKER_CAPABILITY_MISMATCH = "worker_capability_mismatch"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"
    ENVIRONMENT_FAILURE = "environment_failure"
    PERMISSION_BLOCKED = "permission_blocked"
    CONSENT_SCOPE_CHANGED = "consent_scope_changed"
    NEW_DEPENDENCY = "new_dependency"
    CONFLICT_DETECTED = "conflict_detected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ROOT_GAP = "root_gap"


class ReplanAction(str, Enum):
    ADD_CONTEXT = "add_context"
    REVISE_CONTRACT = "revise_contract"
    RETRY_SAME_WORKER = "retry_same_worker"
    SELECT_ANOTHER_WORKER = "select_another_worker"
    SPLIT_NODE = "split_node"
    REQUEST_CONSENT = "request_consent"
    ESCALATE_MAIN_AGENT = "escalate_main_agent"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ReplanRequest:
    task_id: str
    node_id: str
    reason: ReplanReason
    attempt: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReplanDecision:
    action: ReplanAction
    reason: ReplanReason
    explanation: str


@dataclass(slots=True)
class BoundedReplanner:
    max_attempts: int = 2

    def decide(self, request: ReplanRequest) -> ReplanDecision:
        if request.reason == ReplanReason.MISSING_CONTEXT:
            action = ReplanAction.ADD_CONTEXT
        elif request.reason == ReplanReason.CONSENT_SCOPE_CHANGED:
            action = ReplanAction.REQUEST_CONSENT
        elif request.reason == ReplanReason.PERMISSION_BLOCKED:
            action = ReplanAction.ESCALATE_MAIN_AGENT
        elif request.reason == ReplanReason.WORKER_CAPABILITY_MISMATCH:
            action = ReplanAction.SELECT_ANOTHER_WORKER
        elif request.reason == ReplanReason.VERIFICATION_INCONCLUSIVE:
            action = ReplanAction.REVISE_CONTRACT
        elif request.reason == ReplanReason.VERIFICATION_FAILED:
            action = (
                ReplanAction.RETRY_SAME_WORKER
                if request.attempt < self.max_attempts
                else ReplanAction.SPLIT_NODE
            )
        elif request.reason in {
            ReplanReason.ENVIRONMENT_FAILURE,
            ReplanReason.BUDGET_EXHAUSTED,
        }:
            action = ReplanAction.STOP
        else:
            action = ReplanAction.REVISE_CONTRACT
        return ReplanDecision(
            action=action,
            reason=request.reason,
            explanation=request.detail or f"Selected {action.value} for {request.reason.value}.",
        )


def classify_replan_reason(
    verification: "VerificationResult",
    *,
    integration_conflict: bool = False,
    policy_blocked: bool = False,
    environment_failure: bool = False,
) -> ReplanReason | None:
    """Map structured execution markers to a replan reason.

    Prefers structured ``failures`` when available; falls back to legacy
    confidence/issues string classification for backward compatibility.
    """
    if integration_conflict:
        return ReplanReason.CONFLICT_DETECTED
    if policy_blocked:
        return ReplanReason.PERMISSION_BLOCKED
    if environment_failure:
        return ReplanReason.ENVIRONMENT_FAILURE
    if verification.accepted:
        return None

    # --- Prefer structured failures ---
    if verification.failures:
        # Check for non-retryable categories first (policy, environment,
        # integration conflict never retry).
        for f in verification.failures:
            cat = f.category
            # Import at runtime to avoid circular import; compare by value.
            cat_val = cat.value if hasattr(cat, "value") else str(cat)
            if cat_val == "policy_permission":
                return ReplanReason.PERMISSION_BLOCKED
            if cat_val == "environment":
                return ReplanReason.ENVIRONMENT_FAILURE
            if cat_val == "integration_conflict":
                return ReplanReason.CONFLICT_DETECTED
            if cat_val == "missing_context":
                return ReplanReason.MISSING_CONTEXT
        # Check for semantic inconclusive.
        if any(
            (f.category.value if hasattr(f.category, "value") else str(f.category))
            == "semantic_inconclusive"
            for f in verification.failures
        ):
            return ReplanReason.VERIFICATION_INCONCLUSIVE
        # Check for worker failures (retryable).
        if any(
            (f.category.value if hasattr(f.category, "value") else str(f.category))
            == "worker"
            for f in verification.failures
        ):
            return ReplanReason.VERIFICATION_FAILED
        # Deterministic rejection.
        return ReplanReason.VERIFICATION_FAILED

    # --- Legacy fallback: string parsing ---
    checks = {
        issue.split("]", 1)[1].split(":", 1)[0].strip()
        for issue in verification.issues
        if issue.startswith("[") and "]" in issue
    }
    if checks & {"file_exists", "evidence_requirements"}:
        return ReplanReason.MISSING_CONTEXT
    if verification.confidence == "blocked":
        return ReplanReason.ENVIRONMENT_FAILURE
    if verification.confidence == "inconclusive":
        return ReplanReason.VERIFICATION_INCONCLUSIVE
    return ReplanReason.VERIFICATION_FAILED


def _is_retryable_by_failures(verification: "VerificationResult") -> bool:
    """Check structured failures for retryability.

    Returns True only when all non-accepted failures are retryable worker or
    verifier failures.  Policy/permission/environment/consent/integration
    conflicts are never retryable.
    """
    from ..core.contracts import FailureCategory

    non_retryable_categories = {
        FailureCategory.POLICY_PERMISSION,
        FailureCategory.ENVIRONMENT,
        FailureCategory.INTEGRATION_CONFLICT,
    }
    for f in verification.failures:
        if f.category in non_retryable_categories:
            return False
        if not f.retryable and f.category not in {
            FailureCategory.WORKER,
            FailureCategory.SEMANTIC_INCONCLUSIVE,
        }:
            return False
    return True


def decide_retry(
    verification: "VerificationResult",
    contract: "TaskNodeContract",
    attempt: int,
    *,
    integration_conflict: bool = False,
    policy_blocked: bool = False,
    environment_failure: bool = False,
    fallback_available: bool = False,
) -> ReplanDecision | None:
    """Return a bounded action; this function never invokes a worker.

    Retry rules:
    - Total attempts default to at most 2 (``contract.max_attempts``, which
      defaults to 2).
    - Only retryable worker/verifier failures may be retried.
    - Policy, permission, environment, consent, and integration conflicts are
      **never** retried — they escalate or stop immediately.
    - When a fallback worker is available and the failure is retryable, prefer
      ``SELECT_ANOTHER_WORKER`` over ``RETRY_SAME_WORKER``.
    """
    reason = classify_replan_reason(
        verification,
        integration_conflict=integration_conflict,
        policy_blocked=policy_blocked,
        environment_failure=environment_failure,
    )
    if reason is None:
        return None

    # --- Non-retryable reasons: never retry regardless of attempt count ---
    if reason == ReplanReason.PERMISSION_BLOCKED:
        return ReplanDecision(
            action=ReplanAction.ESCALATE_MAIN_AGENT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            f"{reason.value} is non-retryable; escalating.",
        )
    if reason == ReplanReason.ENVIRONMENT_FAILURE:
        return ReplanDecision(
            action=ReplanAction.STOP,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            f"{reason.value} is non-retryable; stopping.",
        )
    if reason == ReplanReason.CONFLICT_DETECTED:
        return ReplanDecision(
            action=ReplanAction.ESCALATE_MAIN_AGENT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            f"{reason.value} is non-retryable; escalating.",
        )
    if reason == ReplanReason.CONSENT_SCOPE_CHANGED:
        return ReplanDecision(
            action=ReplanAction.REQUEST_CONSENT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            f"{reason.value} requires consent; not retrying.",
        )

    # --- Structured-failure check: is the failure retryable? ---
    # Missing context and an inconclusive contract require a graph/orchestrator
    # action rather than blindly retrying the same worker.  Preserve that
    # structured recommendation even though the failure itself is not marked
    # retryable.
    if reason == ReplanReason.MISSING_CONTEXT and attempt < contract.max_attempts:
        return ReplanDecision(
            action=ReplanAction.ADD_CONTEXT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            "missing_context -> add_context.",
        )
    if reason == ReplanReason.VERIFICATION_INCONCLUSIVE and attempt < contract.max_attempts:
        return ReplanDecision(
            action=ReplanAction.REVISE_CONTRACT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            "verification_inconclusive -> revise_contract.",
        )
    if verification.failures and not _is_retryable_by_failures(verification):
        return ReplanDecision(
            action=ReplanAction.ESCALATE_MAIN_AGENT,
            reason=reason,
            explanation=f"Attempt {attempt}/{contract.max_attempts}: "
            f"structured failures indicate non-retryable condition; escalating.",
        )

    # --- Retryable within budget ---
    if attempt < contract.max_attempts:
        if reason == ReplanReason.MISSING_CONTEXT:
            action = ReplanAction.ADD_CONTEXT
        elif reason == ReplanReason.VERIFICATION_INCONCLUSIVE:
            action = ReplanAction.REVISE_CONTRACT
        elif fallback_available:
            action = ReplanAction.SELECT_ANOTHER_WORKER
        else:
            action = ReplanAction.RETRY_SAME_WORKER
    else:
        action = ReplanAction.ESCALATE_MAIN_AGENT
    return ReplanDecision(
        action=action,
        reason=reason,
        explanation=f"Attempt {attempt}/{contract.max_attempts}: {reason.value} -> {action.value}.",
    )
