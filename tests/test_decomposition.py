from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.decompose import (
    DecompositionPlanner,
    DecompositionService,
    ExecutionMode,
    ExecutionShape,
    GraphEdge,
    HardCapabilityRequirements,
    Requirement,
    RequirementKind,
    TaskContractGraph,
    TaskNodeContract,
    TaskSituationBuilder,
    InteractionMode,
    VerificationContract,
    WorkerArm,
    WorkerCapabilities,
    WorkerRegistry,
    match_capabilities,
)
from cost_router.memory import MemoryStore
from cost_router.delegator.runtime import DelegationRuntime, PreparedWorker
from cost_router.core.contracts import (
    Difficulty,
    Evidence,
    Risk,
    RouteDecision,
    Task,
    WorkerResult,
)


def read_only_worker(worker_id: str = "claude-reader") -> WorkerArm:
    return WorkerArm(
        id=worker_id,
        backend="claude_cli",
        harness="claude_code",
        model="claude-test",
        capabilities=WorkerCapabilities(
            tools=frozenset({"read", "grep", "glob"}),
            context_tokens=100_000,
            provider_protocol="harness_native",
        ),
    )


class DecompositionTests(unittest.TestCase):
    def test_fast_path_builds_one_assigned_verifiable_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="analyze the failure", repo=Path(tmp))
            worker = read_only_worker()
            registry = WorkerRegistry({worker.id: worker})
            situation = TaskSituationBuilder().from_task(task, workers=[worker])

            plan = DecompositionPlanner().plan(task, situation, registry)

            self.assertEqual(plan.shape, ExecutionShape.FAST_PATH)
            self.assertEqual(len(plan.graph.nodes), 1)
            node = next(iter(plan.graph.nodes.values()))
            self.assertEqual(node.assigned_worker_id, worker.id)
            self.assertTrue(node.verification.is_verifiable())
            self.assertEqual(plan.graph.requirement_coverage(), {"R1"})

    def test_multiple_deliverables_build_graph_and_persist_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="analyze and document", repo=Path(tmp))
            worker = read_only_worker()
            requirements = [
                Requirement("R1", "Analyze the failure", RequirementKind.DELIVERABLE),
                Requirement("R2", "Write a remediation plan", RequirementKind.DELIVERABLE),
                Requirement("C1", "Do not edit files", RequirementKind.CONSTRAINT),
            ]
            situation = TaskSituationBuilder().from_task(
                task,
                requirements=requirements,
                workers=[worker],
            )
            registry = WorkerRegistry({worker.id: worker})

            plan = DecompositionPlanner().plan(task, situation, registry)

            self.assertEqual(plan.shape, ExecutionShape.GRAPH)
            self.assertEqual(len(plan.graph.nodes), 3)
            self.assertEqual(plan.graph.requirement_coverage(), {"R1", "R2", "C1"})
            self.assertEqual(len(plan.graph.ready_nodes()), 2)
            plan.validate()

            store = MemoryStore(Path(tmp) / "memory.sqlite3")
            store.record_decomposition(task, plan)
            graph = store.graph_summary()
            self.assertEqual(graph["nodes_root_contract"], 1)
            self.assertEqual(graph["nodes_work"], 2)
            self.assertEqual(graph["nodes_merge"], 1)
            self.assertEqual(graph["edges_contains"], 3)
            self.assertEqual(graph["edges_requires"], 2)

    def test_service_persists_plan_and_plan_mode_forces_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writable = root / "example.py"
            writable.write_text("value = 1\n", encoding="utf-8")
            from cost_router.core.contracts import TaskConstraints, TaskMode

            task = Task(
                goal="plan a code change",
                repo=root,
                write_paths=[writable],
                constraints=TaskConstraints(mode=TaskMode.PATCH),
            )
            worker = read_only_worker()
            service = DecompositionService(
                store=MemoryStore(root / "memory.sqlite3"),
                registry=WorkerRegistry({worker.id: worker}),
            )

            plan = service.prepare(task, interaction_mode=InteractionMode.PLAN)

            node = next(iter(plan.graph.nodes.values()))
            self.assertEqual(node.execution_mode, ExecutionMode.READ_ONLY)
            self.assertFalse(node.write_paths)
            self.assertEqual(service.store.graph_summary()["nodes_root_contract"], 1)

    def test_skill_workflow_steps_become_sequential_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="follow the repository skill", repo=Path(tmp))
            worker = read_only_worker()
            situation = TaskSituationBuilder().from_task(
                task,
                active_skills=["example-skill"],
                skill_steps=["Inspect inputs", "Produce the result", "Verify the result"],
                workers=[worker],
            )
            plan = DecompositionPlanner().plan(
                task,
                situation,
                WorkerRegistry({worker.id: worker}),
            )

            self.assertEqual(plan.shape, ExecutionShape.GRAPH)
            work_nodes = [
                node for node in plan.graph.nodes.values() if node.kind.value == "work"
            ]
            self.assertEqual(len(work_nodes), 3)
            requires_edges = [
                edge for edge in plan.graph.edges if edge.edge_type == "requires"
            ]
            self.assertGreaterEqual(len(requires_edges), 2)
            self.assertEqual(plan.graph.requirement_coverage(), {"R1"})

    def test_hard_capabilities_filter_ineligible_workers(self) -> None:
        worker = read_only_worker()
        requirement = HardCapabilityRequirements(
            modalities=frozenset({"text", "image"}),
            tools=frozenset({"read"}),
        )
        match = match_capabilities(requirement, worker)
        self.assertFalse(match.eligible)
        self.assertIn("missing modalities: image", match.reasons)

    def test_planner_rejects_graph_without_eligible_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="analyze", repo=Path(tmp))
            situation = TaskSituationBuilder().from_task(task)
            registry = WorkerRegistry()
            with self.assertRaisesRegex(ValueError, "No eligible worker"):
                DecompositionPlanner().plan(task, situation, registry)

    def test_cycle_rejection_does_not_corrupt_graph(self) -> None:
        verifier = VerificationContract(evidence_requirements=("evidence",))
        first = TaskNodeContract(id="first", objective="first", verification=verifier)
        second = TaskNodeContract(id="second", objective="second", verification=verifier)
        graph = TaskContractGraph(nodes={first.id: first, second.id: second})
        graph.add_edge(GraphEdge("first", "second"))
        with self.assertRaisesRegex(ValueError, "acyclic"):
            graph.add_edge(GraphEdge("second", "first"))
        self.assertEqual(len(graph.edges), 1)


class DelegationRuntimeTests(unittest.TestCase):
    def test_runtime_executes_verifies_and_records_one_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.txt"
            evidence_path.write_text("verified", encoding="utf-8")
            output_path = root / "worker-output.md"
            output_path.write_text("worker output", encoding="utf-8")
            task = Task(goal="inspect evidence", repo=root, paths=[evidence_path])

            def decide(_: Task) -> RouteDecision:
                return RouteDecision(
                    difficulty=Difficulty.SIMPLE,
                    risk=Risk.READ_ONLY,
                    can_delegate=True,
                    backend="test",
                    worker="test-worker",
                    model="test-model",
                    reason="test decision",
                )

            def runner(**_: object) -> WorkerResult:
                return WorkerResult(
                    status="success",
                    summary="Evidence was inspected.",
                    evidence=[Evidence(path="evidence.txt", observation="verified")],
                    next_steps=["Return the verified result."],
                    raw_output_path=output_path,
                )

            def prepare(_: Task) -> PreparedWorker:
                return PreparedWorker(
                    output_file=output_path,
                    command=["test-worker"],
                    prompt="inspect evidence",
                    runner=runner,
                )

            store = MemoryStore(root / "memory.sqlite3")
            outcome = DelegationRuntime(store).dispatch(
                task,
                decide=decide,
                prepare=prepare,
                execute=True,
            )

            self.assertTrue(outcome.verification and outcome.verification.accepted)
            self.assertEqual(len(store.recent_subtasks()), 1)
            self.assertEqual(store.recent_subtasks()[0]["status"], "success")

    def test_runtime_records_backend_exception_as_failed_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = Task(goal="run a failing worker", repo=root)

            def decide(_: Task) -> RouteDecision:
                return RouteDecision(
                    difficulty=Difficulty.SIMPLE,
                    risk=Risk.READ_ONLY,
                    can_delegate=True,
                    backend="test",
                    worker="broken-worker",
                    model="test-model",
                    reason="exercise failure recording",
                )

            def runner(**_: object) -> WorkerResult:
                raise RuntimeError("backend unavailable")

            def prepare(_: Task) -> PreparedWorker:
                return PreparedWorker(
                    output_file=root / "missing-output.md",
                    command=["broken-worker"],
                    prompt="fail",
                    runner=runner,
                )

            store = MemoryStore(root / "memory.sqlite3")
            outcome = DelegationRuntime(store).dispatch(
                task,
                decide=decide,
                prepare=prepare,
                execute=True,
            )

            self.assertEqual(outcome.result and outcome.result.status, "failed")
            self.assertFalse(outcome.verification and outcome.verification.accepted)
            record = store.recent_subtasks()[0]
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["accepted"], 0)


if __name__ == "__main__":
    unittest.main()
