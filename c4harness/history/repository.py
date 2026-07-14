from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .contracts import ExecutionOutcome, PlanSnapshot


class ExecutionHistoryRepository(Protocol):
    """Narrow append/read interface; no worker-facing context access."""

    def append_plan(self, snapshot: PlanSnapshot) -> None: ...

    def append_outcome(self, outcome: ExecutionOutcome) -> None: ...

    def outcomes_for_worker(self, worker_arm_id: str) -> list[ExecutionOutcome]: ...


@dataclass(slots=True)
class InMemoryHistoryRepository:
    """Deterministic reference implementation for application tests."""

    plans: list[PlanSnapshot] = field(default_factory=list)
    outcomes: list[ExecutionOutcome] = field(default_factory=list)

    def append_plan(self, snapshot: PlanSnapshot) -> None:
        self.plans.append(snapshot)

    def append_outcome(self, outcome: ExecutionOutcome) -> None:
        self.outcomes.append(outcome)

    def outcomes_for_worker(self, worker_arm_id: str) -> list[ExecutionOutcome]:
        return [
            outcome
            for outcome in self.outcomes
            if outcome.worker_arm_id == worker_arm_id
        ]

