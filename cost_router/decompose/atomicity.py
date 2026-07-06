"""Deterministic fast/graph and node-atomicity decisions."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.graph import ExecutionShape, NodeKind, TaskNodeContract, TaskSituation
from .operators import choose_primary_split


@dataclass(frozen=True, slots=True)
class ShapeAssessment:
    shape: ExecutionShape
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AtomicityAssessment:
    atomic: bool
    reasons: tuple[str, ...]


def assess_shape(situation: TaskSituation) -> ShapeAssessment:
    proposal = choose_primary_split(situation)
    if proposal is None:
        return ShapeAssessment(
            ExecutionShape.FAST_PATH,
            0.0,
            ("one bounded deliverable has no profitable split",),
        )
    score = float(max(1, len(proposal.objectives) - 1))
    return ShapeAssessment(ExecutionShape.GRAPH, score, proposal.reasons)


def check_atomicity(
    node: TaskNodeContract,
    *,
    eligible_worker_count: int,
    merge_cost_high: bool = False,
) -> AtomicityAssessment:
    reasons: list[str] = []
    if len(node.requirement_refs) > 1:
        reasons.append("node covers multiple required outcomes")
    if not node.objective.strip():
        reasons.append("node objective is empty")
    if not node.verification.is_verifiable():
        reasons.append("node has no executable verifier contract")
    if eligible_worker_count < 1:
        reasons.append("node has no eligible worker")
    if merge_cost_high:
        reasons.append("coordination or merge cost is too high")
    return AtomicityAssessment(not reasons, tuple(reasons))


def should_stop_decomposing(
    node: TaskNodeContract,
    *,
    depth: int,
    max_depth: int = 3,
) -> bool:
    return (
        depth >= max_depth
        or node.kind in {NodeKind.VERIFY, NodeKind.MERGE, NodeKind.DECISION, NodeKind.WAIT}
        or len(node.requirement_refs) <= 1
    )

