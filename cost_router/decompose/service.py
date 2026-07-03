from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..hooks import HookSet
from ..memory import MemoryStore
from ..core.contracts import Task
from .capabilities import WorkerRegistry
from .models import (
    AcceptanceCriterion,
    DecompositionPlan,
    InteractionMode,
    Requirement,
)
from .planner import DecompositionPlanner, TaskSituationBuilder


@dataclass(slots=True)
class DecompositionService:
    """Coordinates grounding, planning, capability checks, hooks, and storage."""

    store: MemoryStore
    registry: WorkerRegistry
    builder: TaskSituationBuilder = field(default_factory=TaskSituationBuilder)
    planner: DecompositionPlanner = field(default_factory=DecompositionPlanner)
    hooks: HookSet = field(default_factory=HookSet)

    def prepare(
        self,
        task: Task,
        *,
        requirements: Iterable[Requirement] | None = None,
        acceptance_criteria: Iterable[AcceptanceCriterion] | None = None,
        interaction_mode: InteractionMode = InteractionMode.EXECUTE,
        active_skills: Iterable[str] = (),
        skill_steps: Iterable[str] = (),
        environment_facts: Iterable[str] = (),
        unresolved_questions: Iterable[str] = (),
    ) -> DecompositionPlan:
        self.hooks.pre_ground(task)
        situation = self.builder.from_task(
            task,
            requirements=requirements,
            acceptance_criteria=acceptance_criteria,
            interaction_mode=interaction_mode,
            active_skills=active_skills,
            skill_steps=skill_steps,
            environment_facts=environment_facts,
            unresolved_questions=unresolved_questions,
            workers=self.registry.workers.values(),
        )
        self.hooks.post_ground(task, situation)
        self.hooks.pre_decompose(situation)
        plan = self.planner.plan(task, situation, self.registry)
        self.hooks.post_decompose(situation, plan)
        self.store.record_decomposition(task, plan)
        return plan
