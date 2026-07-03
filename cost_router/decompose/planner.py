from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.contracts import Task, TaskMode
from .capabilities import WorkerRegistry
from .models import (
    AcceptanceCriterion,
    DecompositionPlan,
    ExecutionMode,
    ExecutionShape,
    GraphEdge,
    HardCapabilityRequirements,
    InteractionMode,
    NodeKind,
    Requirement,
    RequirementKind,
    RequirementLedger,
    RootContract,
    TaskContractGraph,
    TaskNodeContract,
    TaskSituation,
    VerificationContract,
    WorkerArm,
)


@dataclass(slots=True)
class TaskSituationBuilder:
    """Builds an explicit situation from already-grounded inputs.

    Requirement extraction from free-form chat and Skill workflow parsing belong
    above this boundary. Keeping the builder deterministic makes the resulting
    contract straightforward to test and audit.
    """

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
    ) -> TaskSituation:
        ledger_items = list(requirements or ())
        if not ledger_items:
            ledger_items = [
                Requirement("R1", task.goal, RequirementKind.DELIVERABLE)
            ]
        ledger = RequirementLedger(ledger_items)

        criteria = list(acceptance_criteria or ())
        if not criteria:
            criteria = [
                AcceptanceCriterion(
                    id="A1",
                    description="Produce an evidence-backed result for the requested goal.",
                    requirement_refs=tuple(sorted(ledger.required_ids())),
                )
            ]

        constraints = [f"task_mode={task.constraints.mode.value}"]
        if not task.constraints.allow_network:
            constraints.append("network=deny")
        if task.write_paths:
            constraints.append(
                "write_paths=" + ",".join(str(path) for path in task.write_paths)
            )

        return TaskSituation(
            task_id=task.id,
            objective=task.goal,
            repo=task.repo,
            requirements=ledger,
            root_contract=RootContract(criteria),
            interaction_mode=interaction_mode,
            active_skills=tuple(active_skills),
            skill_steps=tuple(skill_steps),
            constraints=tuple(constraints),
            environment_facts=tuple(environment_facts),
            unresolved_questions=tuple(unresolved_questions),
            available_worker_ids=tuple(worker.id for worker in workers),
        )


@dataclass(slots=True)
class DecompositionPlanner:
    max_work_nodes: int = 5

    def plan(
        self,
        task: Task,
        situation: TaskSituation,
        registry: WorkerRegistry | None = None,
    ) -> DecompositionPlan:
        deliverables = situation.requirements.deliverables()
        graph_reasons = self._graph_reasons(situation, deliverables)
        if not graph_reasons:
            plan = self._fast_path(task, situation)
        else:
            plan = self._graph_path(task, situation, deliverables, graph_reasons)
        if registry is not None:
            self._assign_workers(plan, registry)
        plan.validate()
        return plan

    def _assign_workers(
        self,
        plan: DecompositionPlan,
        registry: WorkerRegistry,
    ) -> None:
        for node in plan.graph.nodes.values():
            eligible = registry.eligible(node.hard_capabilities)
            if not eligible:
                raise ValueError(
                    f"No eligible worker for node {node.id}: {node.objective}"
                )
            node.assigned_worker_id = max(
                eligible,
                key=lambda worker: sum(
                    weight * worker.capabilities.soft.get(dimension, 0.0)
                    for dimension, weight in node.soft_capabilities.items()
                ),
            ).id
            plan.reasons.append(
                f"{node.id} assigned to {node.assigned_worker_id} after hard-capability filtering"
            )

    def _graph_reasons(
        self,
        situation: TaskSituation,
        deliverables: list[Requirement],
    ) -> list[str]:
        reasons: list[str] = []
        if len(deliverables) > 1:
            reasons.append("multiple independently traceable deliverables")
        if len(situation.skill_steps) > 1:
            reasons.append("multi-stage Skill workflow")
        if situation.unresolved_questions:
            reasons.append("grounding requires bounded probe work")
        return reasons

    def _fast_path(self, task: Task, situation: TaskSituation) -> DecompositionPlan:
        node = self._work_node(task, situation, situation.requirements.items, task.goal)
        graph = TaskContractGraph(nodes={node.id: node})
        return DecompositionPlan(
            situation=situation,
            shape=ExecutionShape.FAST_PATH,
            graph=graph,
            reasons=["one verifiable deliverable can be handled by one worker session"],
        )

    def _graph_path(
        self,
        task: Task,
        situation: TaskSituation,
        deliverables: list[Requirement],
        reasons: list[str],
    ) -> DecompositionPlan:
        graph = TaskContractGraph()
        prerequisite_ids: list[str] = []

        if situation.unresolved_questions:
            probe = TaskNodeContract(
                kind=NodeKind.PROBE,
                objective="Resolve task-blocking questions with repository evidence.",
                allowed_paths=tuple(task.paths),
                context_packs=tuple(task.context_packs),
                verification=VerificationContract(
                    evidence_requirements=("Cite the artifact or repository fact for each answer.",),
                    root_contribution="Provides facts required for stable decomposition.",
                ),
            )
            graph.add_node(probe)
            prerequisite_ids.append(probe.id)

        if len(situation.skill_steps) > 1:
            work_specs = [
                (
                    step,
                    situation.requirements.items
                    if index == len(situation.skill_steps) - 1
                    else [],
                )
                for index, step in enumerate(situation.skill_steps)
            ]
        else:
            work_specs = [
                (requirement.text, [requirement])
                for requirement in (deliverables or situation.requirements.items)
            ]
        if len(work_specs) > self.max_work_nodes:
            raise ValueError(
                f"Initial graph exceeds max_work_nodes={self.max_work_nodes}; "
                "group or prioritize requirements before planning."
            )

        work_ids: list[str] = []
        previous_work_id: str | None = None
        for objective, covered_requirements in work_specs:
            node = self._work_node(task, situation, covered_requirements, objective)
            graph.add_node(node)
            work_ids.append(node.id)
            for prerequisite_id in prerequisite_ids:
                graph.add_edge(GraphEdge(prerequisite_id, node.id))
            if len(situation.skill_steps) > 1 and previous_work_id:
                graph.add_edge(GraphEdge(previous_work_id, node.id))
            previous_work_id = node.id

        if len(work_ids) > 1:
            merge = TaskNodeContract(
                kind=NodeKind.MERGE,
                objective="Merge worker outputs and check complete requirement coverage.",
                requirement_refs=tuple(sorted(situation.requirements.required_ids())),
                output_type="integrated_result",
                verification=VerificationContract(
                    evidence_requirements=("Map every required requirement to a result.",),
                    semantic_check="Check that outputs are mutually consistent.",
                    root_contribution="Produces the integrated result for root verification.",
                ),
            )
            graph.add_node(merge)
            for work_id in work_ids:
                graph.add_edge(GraphEdge(work_id, merge.id))

        return DecompositionPlan(
            situation=situation,
            shape=ExecutionShape.GRAPH,
            graph=graph,
            reasons=reasons,
        )

    def _work_node(
        self,
        task: Task,
        situation: TaskSituation,
        requirements: Iterable[Requirement],
        objective: str,
    ) -> TaskNodeContract:
        requirement_refs = tuple(item.id for item in requirements if item.required)
        execution_mode = ExecutionMode.READ_ONLY
        if (
            situation.interaction_mode != InteractionMode.PLAN
            and task.constraints.mode == TaskMode.PATCH
        ):
            execution_mode = ExecutionMode.PATCH
        write_paths = tuple(task.write_paths) if execution_mode == ExecutionMode.PATCH else ()
        tools = {"read"}
        write_isolation: frozenset[str] = frozenset()
        if execution_mode == ExecutionMode.PATCH:
            tools.add("patch")
            write_isolation = frozenset({"staged_copy", "worktree"})
        return TaskNodeContract(
            kind=NodeKind.WORK,
            objective=objective,
            requirement_refs=requirement_refs,
            context_packs=tuple(task.context_packs),
            allowed_paths=tuple(task.paths),
            write_paths=write_paths,
            output_type="patch" if execution_mode == ExecutionMode.PATCH else "report",
            execution_mode=execution_mode,
            hard_capabilities=HardCapabilityRequirements(
                tools=frozenset(tools),
                write_isolation=write_isolation,
            ),
            verification=VerificationContract(
                evidence_requirements=("Provide inspectable evidence for the result.",),
                semantic_check="Check the result against the node objective.",
                root_contribution="Satisfies " + ", ".join(requirement_refs),
            ),
        )
