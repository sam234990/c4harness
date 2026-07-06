from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..core.graph import DecompositionPlan


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class FailureAttribution(str, Enum):
    NONE = "none"
    WORKER_ERROR = "worker_error"
    DECOMPOSITION_ERROR = "decomposition_error"
    ASSIGNMENT_ERROR = "assignment_error"
    MISSING_CONTEXT = "missing_context"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"
    ENVIRONMENT_FAILURE = "environment_failure"
    PERMISSION_BLOCKED = "permission_blocked"
    CONSENT_SCOPE_CHANGED = "consent_scope_changed"
    INTEGRATION_CONFLICT = "integration_conflict"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    """Immutable cross-task record of a decomposition plan version."""

    task_id: str
    version: int
    payload: dict[str, Any]
    recorded_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_plan(cls, plan: DecompositionPlan) -> "PlanSnapshot":
        return cls(
            task_id=plan.situation.task_id,
            version=plan.graph.version,
            payload=plan.to_dict(),
        )


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """Append-only fact about one assigned node execution."""

    task_id: str
    node_id: str
    worker_arm_id: str | None
    status: OutcomeStatus
    capability_dimensions: tuple[str, ...] = ()
    verification_status: str | None = None
    failure_attribution: FailureAttribution = FailureAttribution.NONE
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    artifact_refs: tuple[str, ...] = ()
    recorded_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    worker_arm_id: str
    capability_dimension: str
    verified_successes: int = 0
    verified_failures: int = 0
    inconclusive_count: int = 0
    excluded_count: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0

    @property
    def usable_sample_count(self) -> int:
        return self.verified_successes + self.verified_failures

