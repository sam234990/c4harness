from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..core.contracts import Task, TaskMode
from .capabilities import WorkerRegistry
from .assignment import WorkerAssignmentPolicy
from .atomicity import assess_shape
from .models import (
    DecompositionPlan,
    ExecutionMode,
    ExecutionShape,
    GraphEdge,
    HardCapabilityRequirements,
    InteractionMode,
    NodeKind,
    Requirement,
    TaskContractGraph,
    TaskNodeContract,
    TaskSituation,
    VerificationContract,
)
from .situation import TaskSituationBuilder
from .operators import choose_primary_split, requirements_for_objective


@dataclass(slots=True)
class DecompositionPlanner:
    max_work_nodes: int = 5
    assignment_policy: WorkerAssignmentPolicy = field(
        default_factory=WorkerAssignmentPolicy
    )
    worker_preferences: dict[str, float] = field(default_factory=dict)
    capability_profiles: dict[str, object] = field(default_factory=dict)

    def plan(
        self,
        task: Task,
        situation: TaskSituation,
        registry: WorkerRegistry | None = None,
    ) -> DecompositionPlan:
        deliverables = situation.requirements.deliverables()
        shape = assess_shape(situation)
        graph_reasons = list(shape.reasons)
        if shape.shape == ExecutionShape.FAST_PATH:
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
            assignment = self.assignment_policy.assign(
                node,
                registry,
                worker_preferences=self.worker_preferences,
                capability_profiles=self.capability_profiles,  # type: ignore[arg-type]
                verifier_available=node.verification.is_verifiable(),
            )
            node.assigned_worker_id = assignment.worker_id
            record = assignment.to_dict()
            worker = registry.get(assignment.worker_id)
            record["risk_manifest"] = {
                "destination": f"{worker.harness}:{worker.model}",
                "privacy_zone": worker.capabilities.privacy_zone,
                "transmitted_paths": [str(path) for path in (*node.allowed_paths, *node.context_packs)],
                "write_paths": [str(path) for path in node.write_paths],
                "execution_mode": node.execution_mode.value,
                "persistent_session": node.hard_capabilities.persistent_session_required,
                "callback": False,
                "consent_required": worker.capabilities.privacy_zone == "approved_external",
            }
            plan.assignment_records[node.id] = record
            plan.reasons.append(
                f"{node.id} assigned to {node.assigned_worker_id} after "
                f"hard-capability filtering (confidence={assignment.confidence:.2f})"
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

        proposal = choose_primary_split(situation)
        if proposal and proposal.operator == "workflow_split":
            work_specs = [
                (objective, situation.requirements.items if index == len(proposal.objectives) - 1 else [])
                for index, objective in enumerate(proposal.objectives)
            ]
        elif proposal:
            work_specs = [
                (objective, requirements_for_objective(situation, objective))
                for objective in proposal.objectives
                if objective != "Resolve task-blocking questions with repository evidence."
            ]
        else:
            work_specs = [(task.goal, situation.requirements.items)]
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
