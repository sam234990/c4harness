"""Explainable hard-filter and soft-score worker assignment."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.graph import TaskNodeContract, WorkerArm
from ..history import CapabilityProfile
from .capabilities import CapabilityMatch, WorkerRegistry
from .confidence import ConfidenceFactors, compute_confidence


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    soft_capability: float = 0.0
    preference_bias: float = 0.0
    quality_evidence: float = 0.0
    expected_tokens: float = 0.0
    expected_latency: float = 0.0
    operational_risk: float = 0.0
    uncertainty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.soft_capability
            + self.preference_bias
            + self.quality_evidence
            - self.expected_tokens
            - self.expected_latency
            - self.operational_risk
            - self.uncertainty
        )

    def to_dict(self) -> dict[str, float]:
        return {**{name: getattr(self, name) for name in self.__dataclass_fields__}, "total": self.total}


@dataclass(frozen=True, slots=True)
class AssignmentCandidate:
    worker_id: str
    eligible: bool
    score: float
    reasons: tuple[str, ...]
    breakdown: ScoreBreakdown | None = None
    hard_capability_match: CapabilityMatch | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "eligible": self.eligible,
            "score": self.score,
            "reasons": list(self.reasons),
            "breakdown": self.breakdown.to_dict() if self.breakdown else None,
        }


@dataclass(frozen=True, slots=True)
class AssignmentDecision:
    worker_id: str
    candidates: tuple[AssignmentCandidate, ...]
    confidence: float
    confidence_factors: ConfidenceFactors

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "confidence": self.confidence,
            "confidence_factors": self.confidence_factors.to_dict(),
        }


def _history_signal(node: TaskNodeContract, profile: CapabilityProfile | None) -> tuple[float, int]:
    if profile is None:
        return 0.5, 0
    relevant = [
        evidence
        for evidence in profile.evidence
        if not node.soft_capabilities or evidence.capability_dimension in node.soft_capabilities
    ]
    samples = sum(item.usable_sample_count for item in relevant)
    successes = sum(item.verified_successes for item in relevant)
    return ((successes / samples) if samples else 0.5), samples


@dataclass(slots=True)
class WorkerAssignmentPolicy:
    preference_weight: float = 0.10
    history_weight: float = 0.20
    token_weight: float = 0.05
    latency_weight: float = 0.05
    risk_weight: float = 0.10
    uncertainty_weight: float = 0.10

    def assign(
        self,
        node: TaskNodeContract,
        registry: WorkerRegistry,
        *,
        worker_preferences: dict[str, float] | None = None,
        capability_profiles: dict[str, CapabilityProfile] | None = None,
        token_estimates: dict[str, float] | None = None,
        latency_estimates: dict[str, float] | None = None,
        risk_estimates: dict[str, float] | None = None,
        verifier_available: bool = True,
    ) -> AssignmentDecision:
        preferences = worker_preferences or {}
        profiles = capability_profiles or {}
        token = token_estimates or {}
        latency = latency_estimates or {}
        risk = risk_estimates or {}
        matches = registry.evaluate(node.hard_capabilities)
        candidates: list[AssignmentCandidate] = []
        ranked: list[tuple[float, str, WorkerArm, int]] = []

        for worker in registry.workers.values():
            match = matches[worker.id]
            if not match.eligible:
                candidates.append(AssignmentCandidate(worker.id, False, 0.0, match.reasons, None, match))
                continue
            soft = sum(
                weight * worker.capabilities.soft.get(dimension, 0.0)
                for dimension, weight in node.soft_capabilities.items()
            )
            quality, samples = _history_signal(node, profiles.get(worker.id))
            uncertainty = 1.0 / (1.0 + samples)
            breakdown = ScoreBreakdown(
                soft_capability=soft,
                preference_bias=self.preference_weight * preferences.get(worker.id, 0.0),
                quality_evidence=self.history_weight * quality,
                expected_tokens=self.token_weight * token.get(worker.id, 0.0),
                expected_latency=self.latency_weight * latency.get(worker.id, 0.0),
                operational_risk=self.risk_weight * risk.get(worker.id, 0.0),
                uncertainty=self.uncertainty_weight * uncertainty,
            )
            candidates.append(AssignmentCandidate(worker.id, True, breakdown.total, ("passed hard-capability requirements",), breakdown, match))
            ranked.append((breakdown.total, worker.id, worker, samples))

        if not ranked:
            detail = "; ".join(f"{item.worker_id}: {', '.join(item.reasons)}" for item in candidates)
            raise ValueError(f"No eligible worker for node {node.id}: {node.objective}; {detail}")
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected_score, _, selected, samples = ranked[0]
        margin = selected_score - ranked[1][0] if len(ranked) > 1 else 0.5
        factors = ConfidenceFactors(
            capability_match=1.0,
            task_coverage=1.0,
            evidence_samples=samples,
            verifier_available=verifier_available,
            score_margin=max(0.0, margin),
        )
        return AssignmentDecision(selected.id, tuple(candidates), compute_confidence(factors), factors)

