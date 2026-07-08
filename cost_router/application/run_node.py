from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import Task
from ..delegator.runtime import (
    DecisionFactory,
    DelegationOutcome,
    DelegationRuntime,
    PreparationFactory,
    Verifier,
)


@dataclass(slots=True)
class RunNode:
    """Thin use case around the existing one-node delegation runtime."""

    runtime: DelegationRuntime

    def execute(
        self,
        task: Task,
        *,
        decide: DecisionFactory,
        prepare: PreparationFactory,
        execute: bool,
        node_id: str = "default",
        worker_arm_id: str | None = None,
        capability_dimensions: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        verifier: Verifier | None = None,
    ) -> DelegationOutcome:
        return self.runtime.dispatch(
            task,
            decide=decide,
            prepare=prepare,
            execute=execute,
            node_id=node_id,
            worker_arm_id=worker_arm_id,
            capability_dimensions=capability_dimensions,
            artifact_refs=artifact_refs,
            verifier=verifier,
        )
