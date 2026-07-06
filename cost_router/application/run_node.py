from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import Task
from ..delegator.runtime import (
    DecisionFactory,
    DelegationOutcome,
    DelegationRuntime,
    PreparationFactory,
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
    ) -> DelegationOutcome:
        return self.runtime.dispatch(
            task,
            decide=decide,
            prepare=prepare,
            execute=execute,
        )

