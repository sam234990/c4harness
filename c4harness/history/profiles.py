from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    CapabilityEvidence,
    ExecutionOutcome,
    FailureAttribution,
    OutcomeStatus,
)


_EXCLUDED_ATTRIBUTIONS = {
    FailureAttribution.ENVIRONMENT_FAILURE,
    FailureAttribution.PERMISSION_BLOCKED,
    FailureAttribution.CONSENT_SCOPE_CHANGED,
    FailureAttribution.MISSING_CONTEXT,
    FailureAttribution.DECOMPOSITION_ERROR,
    FailureAttribution.ASSIGNMENT_ERROR,
    FailureAttribution.INTEGRATION_CONFLICT,
}


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    worker_arm_id: str
    evidence: tuple[CapabilityEvidence, ...]


def build_capability_profile(
    worker_arm_id: str,
    outcomes: list[ExecutionOutcome],
) -> CapabilityProfile:
    buckets: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        if outcome.worker_arm_id != worker_arm_id:
            continue
        dimensions = outcome.capability_dimensions or ("general",)
        for dimension in dimensions:
            bucket = buckets.setdefault(
                dimension,
                {
                    "success": 0,
                    "failure": 0,
                    "inconclusive": 0,
                    "excluded": 0,
                    "tokens": 0,
                    "latency": 0,
                },
            )
            bucket["tokens"] += outcome.total_tokens or 0
            bucket["latency"] += outcome.latency_ms or 0
            if outcome.failure_attribution in _EXCLUDED_ATTRIBUTIONS:
                bucket["excluded"] += 1
            elif outcome.status == OutcomeStatus.SUCCESS:
                bucket["success"] += 1
            elif outcome.status == OutcomeStatus.FAILED:
                bucket["failure"] += 1
            else:
                bucket["inconclusive"] += 1

    evidence = tuple(
        CapabilityEvidence(
            worker_arm_id=worker_arm_id,
            capability_dimension=dimension,
            verified_successes=values["success"],
            verified_failures=values["failure"],
            inconclusive_count=values["inconclusive"],
            excluded_count=values["excluded"],
            total_tokens=values["tokens"],
            total_latency_ms=values["latency"],
        )
        for dimension, values in sorted(buckets.items())
    )
    return CapabilityProfile(worker_arm_id=worker_arm_id, evidence=evidence)
