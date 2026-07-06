"""Explainable first-version decomposition operators."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.graph import Requirement, TaskSituation


@dataclass(frozen=True, slots=True)
class SplitProposal:
    operator: str
    objectives: tuple[str, ...]
    sequential: bool
    reasons: tuple[str, ...]


def deliverable_split(situation: TaskSituation) -> SplitProposal | None:
    items = situation.requirements.deliverables()
    if len(items) < 2:
        return None
    return SplitProposal(
        "deliverable_split",
        tuple(item.text for item in items),
        False,
        ("multiple independently traceable deliverables",),
    )


def workflow_split(situation: TaskSituation) -> SplitProposal | None:
    if len(situation.skill_steps) < 2:
        return None
    return SplitProposal(
        "workflow_split",
        situation.skill_steps,
        True,
        ("multi-stage Skill workflow",),
    )


def evidence_split(situation: TaskSituation) -> SplitProposal | None:
    if not situation.unresolved_questions:
        return None
    return SplitProposal(
        "evidence_split",
        ("Resolve task-blocking questions with repository evidence.", situation.objective),
        True,
        ("grounding requires bounded probe work",),
    )


def capability_split(situation: TaskSituation) -> SplitProposal | None:
    needs_write = any("write_paths=" in item for item in situation.constraints)
    if not needs_write or len(situation.available_worker_ids) < 2:
        return None
    return SplitProposal(
        "capability_split",
        ("Perform bounded read-only analysis.", "Implement the verified change."),
        True,
        ("analysis and patch execution require different capabilities",),
    )


def risk_split(situation: TaskSituation) -> SplitProposal | None:
    private_external = {
        "data_classification=private",
        "external_policy=allow",
    }.issubset(set(situation.constraints))
    if not private_external:
        return None
    return SplitProposal(
        "risk_split",
        ("Prepare the minimum external context scope.", situation.objective),
        True,
        ("private external delegation requires a consent gate",),
    )


def verification_split(situation: TaskSituation) -> SplitProposal | None:
    deliverables = situation.requirements.deliverables()
    if len(deliverables) < 2:
        return None
    return SplitProposal(
        "verification_split",
        ("Verify cross-deliverable consistency and requirement coverage.",),
        True,
        ("multiple outputs require integration verification",),
    )


def choose_primary_split(situation: TaskSituation) -> SplitProposal | None:
    """Select one stable initial shape; other operators remain planning signals."""
    return (
        workflow_split(situation)
        or deliverable_split(situation)
        or evidence_split(situation)
        or capability_split(situation)
        or risk_split(situation)
    )


def requirements_for_objective(
    situation: TaskSituation, objective: str
) -> list[Requirement]:
    matching = [item for item in situation.requirements.deliverables() if item.text == objective]
    return matching or list(situation.requirements.items)

