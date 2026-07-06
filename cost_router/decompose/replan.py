from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

