"""Transparent, non-probabilistic assignment confidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfidenceFactors:
    capability_match: float
    task_coverage: float
    evidence_samples: int
    verifier_available: bool
    score_margin: float = 0.0

    def to_dict(self) -> dict[str, float | int | bool]:
        return {
            "capability_match": self.capability_match,
            "task_coverage": self.task_coverage,
            "evidence_samples": self.evidence_samples,
            "verifier_available": self.verifier_available,
            "score_margin": self.score_margin,
        }


def compute_confidence(factors: ConfidenceFactors) -> float:
    evidence = factors.evidence_samples / (factors.evidence_samples + 5.0)
    verifier = 1.0 if factors.verifier_available else 0.6
    margin = min(1.0, factors.score_margin)
    value = (
        0.30 * factors.capability_match
        + 0.20 * factors.task_coverage
        + 0.25 * evidence
        + 0.15 * verifier
        + 0.10 * margin
    )
    return max(0.0, min(1.0, value))

