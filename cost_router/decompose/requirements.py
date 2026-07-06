"""Requirement-ledger and root-contract construction helpers."""

from __future__ import annotations

from collections.abc import Iterable

from ..core.graph import (
    AcceptanceCriterion,
    Requirement,
    RequirementKind,
    RequirementLedger,
    RootContract,
)


def build_requirement_ledger(
    objective: str,
    requirements: Iterable[Requirement] | None = None,
) -> RequirementLedger:
    items = list(requirements or ())
    if not items:
        items = [Requirement("R1", objective, RequirementKind.DELIVERABLE)]
    return RequirementLedger(items)


def build_root_contract(
    ledger: RequirementLedger,
    criteria: Iterable[AcceptanceCriterion] | None = None,
) -> RootContract:
    items = list(criteria or ())
    if not items:
        items = [
            AcceptanceCriterion(
                id="A1",
                description="Produce an evidence-backed result for the requested goal.",
                requirement_refs=tuple(sorted(ledger.required_ids())),
            )
        ]
    return RootContract(items)


__all__ = [
    "AcceptanceCriterion",
    "Requirement",
    "RequirementKind",
    "RequirementLedger",
    "RootContract",
    "build_requirement_ledger",
    "build_root_contract",
]

