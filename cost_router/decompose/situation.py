"""Deterministic TaskSituation construction from already-grounded inputs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..core.contracts import Task
from ..core.graph import (
    AcceptanceCriterion,
    InteractionMode,
    Requirement,
    TaskSituation,
    WorkerArm,
)
from .requirements import build_requirement_ledger, build_root_contract


@dataclass(slots=True)
class TaskSituationBuilder:
    """Build private orchestrator state without free-form LLM extraction."""

    def from_task(
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
        workers: Iterable[WorkerArm] = (),
        historical_profile_summary: Iterable[str] = (),
        security_context: Iterable[str] = (),
    ) -> TaskSituation:
        ledger = build_requirement_ledger(task.goal, requirements)
        root_contract = build_root_contract(ledger, acceptance_criteria)
        constraints = [f"task_mode={task.constraints.mode.value}"]
        if not task.constraints.allow_network:
            constraints.append("network=deny")
        if task.write_paths:
            constraints.append(
                "write_paths=" + ",".join(str(path) for path in task.write_paths)
            )
        constraints.extend(
            [
                f"external_policy={task.constraints.external_policy.value}",
                f"data_classification={task.constraints.data_classification.value}",
            ]
        )
        return TaskSituation(
            task_id=task.id,
            objective=task.goal,
            repo=task.repo,
            requirements=ledger,
            root_contract=root_contract,
            interaction_mode=interaction_mode,
            active_skills=tuple(active_skills),
            skill_steps=tuple(skill_steps),
            constraints=tuple(constraints),
            environment_facts=tuple(environment_facts),
            unresolved_questions=tuple(unresolved_questions),
            available_worker_ids=tuple(worker.id for worker in workers),
            historical_profile_summary=tuple(historical_profile_summary),
            security_context=tuple(security_context),
        )


__all__ = ["TaskSituation", "TaskSituationBuilder"]

