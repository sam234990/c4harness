from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.contracts import Task
from ..core.graph import DecompositionPlan
from ..decompose.service import DecompositionService
from ..history import ExecutionHistoryRepository, PlanSnapshot


@dataclass(slots=True)
class PrepareTask:
    """Application boundary for decomposition and optional history recording."""

    decomposer: DecompositionService
    history: ExecutionHistoryRepository | None = None

    def execute(self, task: Task, **grounding: Any) -> DecompositionPlan:
        plan = self.decomposer.prepare(task, **grounding)
        if self.history is not None:
            self.history.append_plan(PlanSnapshot.from_plan(plan))
        return plan

