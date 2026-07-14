"""Integration tests for the Phase 2/3 application execution boundary."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from c4harness.application import GraphExecutionService
from c4harness.core.contracts import (
    Difficulty,
    Evidence,
    Risk,
    RouteDecision,
    Task,
    WorkerResult,
)
from c4harness.core.graph import (
    AcceptanceCriterion,
    DecompositionPlan,
    ExecutionShape,
    GraphEdge,
    Requirement,
    RequirementLedger,
    RootContract,
    TaskContractGraph,
    TaskNodeContract,
    TaskSituation,
    VerificationContract,
)
from c4harness.delegator import DelegationRuntime, NodeState, PreparedWorker
from c4harness.history import InMemoryHistoryRepository
from c4harness.memory import MemoryStore


def _plan(repo: Path) -> DecompositionPlan:
    requirements = RequirementLedger([Requirement("R1", "Produce verified output")])
    root = RootContract([
        AcceptanceCriterion(
            "A1",
            "Output exists",
            check="file_exists",
            requirement_refs=("R1",),
        )
    ])
    situation = TaskSituation(
        task_id="root-task",
        objective="complete a two-node workflow",
        repo=repo,
        requirements=requirements,
        root_contract=root,
    )
    first = TaskNodeContract(
        id="inspect",
        objective="inspect inputs",
        requirement_refs=("R1",),
        allowed_paths=(repo / "artifact.txt",),
        assigned_worker_id="worker-a",
        verification=VerificationContract(
            deterministic_checks=("file_exists:artifact.txt",),
            root_contribution="Supports R1",
        ),
    )
    second = TaskNodeContract(
        id="confirm",
        objective="confirm output",
        requirement_refs=("R1",),
        allowed_paths=(repo / "artifact.txt",),
        assigned_worker_id="worker-a",
        verification=VerificationContract(
            deterministic_checks=("file_exists:artifact.txt",),
            root_contribution="Completes R1",
        ),
    )
    graph = TaskContractGraph(nodes={first.id: first, second.id: second})
    graph.add_edge(GraphEdge("inspect", "confirm"))
    plan = DecompositionPlan(situation, ExecutionShape.GRAPH, graph)
    plan.validate()
    return plan


def _decision(worker: str) -> RouteDecision:
    return RouteDecision(
        difficulty=Difficulty.SIMPLE,
        risk=Risk.READ_ONLY,
        can_delegate=True,
        backend="fake",
        worker=worker,
        model="fake",
        reason="integration test",
    )


class GraphExecutionIntegrationTests(unittest.TestCase):
    def test_graph_delegates_verifies_records_history_and_verifies_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            artifact = repo / "artifact.txt"
            artifact.write_text("verified")
            (repo / "inspect.evidence").write_text("verified")
            (repo / "confirm.evidence").write_text("verified")
            plan = _plan(repo)
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(
                MemoryStore(repo / "memory.sqlite3"),
                history=history,
            )

            def prepare(node, task):
                def runner(**_):
                    return WorkerResult(
                        status="success",
                        summary=f"completed {node.id}",
                        evidence=[Evidence(f"{node.id}.evidence", "verified")],
                        next_steps=["continue"],
                    )
                return PreparedWorker(repo / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision(node.assigned_worker_id or "worker-a"),
                prepare=prepare,
            )
            report = service.execute(plan, Task("root", repo=repo))

            self.assertTrue(report.accepted)
            self.assertEqual(report.graph_result.execution_order, ["inspect", "confirm"])
            self.assertEqual(set(report.node_verifications), {"inspect", "confirm"})
            self.assertEqual(len(history.outcomes), 2)
            self.assertTrue(all(item.status.value == "success" for item in history.outcomes))
            self.assertTrue(json.dumps(report.to_dict()))

    def test_failed_node_blocks_downstream_and_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "artifact.txt").write_text("verified")
            plan = _plan(repo)
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(MemoryStore(repo / "memory.sqlite3"), history=history)

            def prepare(node, task):
                def runner(**_):
                    return WorkerResult(
                        status="failed" if node.id == "inspect" else "success",
                        summary="failed" if node.id == "inspect" else "done",
                        evidence=[Evidence("artifact.txt", "verified")],
                        next_steps=["inspect failure"],
                    )
                return PreparedWorker(repo / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision("worker-a"),
                prepare=prepare,
            )
            report = service.execute(plan, Task("root", repo=repo))

            self.assertFalse(report.accepted)
            self.assertEqual(report.graph_result.node_outcomes["inspect"].state, NodeState.FAILED)
            self.assertEqual(report.graph_result.node_outcomes["confirm"].state, NodeState.BLOCKED)
        # Default graph nodes receive one initial attempt plus one bounded
        # retry/fallback attempt.
        self.assertEqual(len(history.outcomes), 2)

    def test_dry_run_does_not_delegate_or_write_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "artifact.txt").write_text("verified")
            plan = _plan(repo)
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(MemoryStore(repo / "memory.sqlite3"), history=history)
            calls: list[str] = []

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision("worker-a"),
                prepare=lambda node, task: calls.append(node.id),
            )
            report = service.execute(plan, Task("root", repo=repo), execute=False)

            self.assertTrue(report.graph_result.all_succeeded)
            self.assertIsNone(report.root_verification)
            self.assertEqual(calls, [])
            self.assertEqual(history.outcomes, [])


if __name__ == "__main__":
    unittest.main()
