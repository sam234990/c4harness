"""End-to-end graph workspace, verifier, bounded retry and parallel tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from c4harness.application import GraphExecutionService
from c4harness.core.contracts import Difficulty, Evidence, Risk, RouteDecision, Task, WorkerResult
from c4harness.core.graph import (
    AcceptanceCriterion,
    DecompositionPlan,
    ExecutionMode,
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
from c4harness.delegator import DelegationRuntime, PreparedWorker
from c4harness.history import FailureAttribution, InMemoryHistoryRepository, OutcomeStatus
from c4harness.hooks import HookSet
from c4harness.memory import MemoryStore


def _decision(worker: str) -> RouteDecision:
    return RouteDecision(
        Difficulty.SIMPLE,
        Risk.PATCH,
        True,
        "fake",
        worker,
        "fake",
        "test",
    )


def _plan(repo: Path, nodes: list[TaskNodeContract]) -> DecompositionPlan:
    requirements = RequirementLedger([Requirement("R1", "Integrate verified output")])
    situation = TaskSituation(
        task_id="graph-task",
        objective="integrate sequential patches",
        repo=repo,
        requirements=requirements,
        root_contract=RootContract(
            [AcceptanceCriterion("A1", "Output integrated", "file_exists", ("R1",))]
        ),
    )
    graph = TaskContractGraph(nodes={node.id: node for node in nodes})
    for left, right in zip(nodes, nodes[1:]):
        graph.add_edge(GraphEdge(left.id, right.id))
    plan = DecompositionPlan(situation, ExecutionShape.GRAPH, graph)
    plan.validate()
    return plan


def _independent_plan(repo: Path, nodes: list[TaskNodeContract]) -> DecompositionPlan:
    """Build a plan with no edges between nodes (all independent)."""
    requirements = RequirementLedger([Requirement("R1", "Integrate verified output")])
    situation = TaskSituation(
        task_id="graph-task",
        objective="integrate parallel patches",
        repo=repo,
        requirements=requirements,
        root_contract=RootContract(
            [AcceptanceCriterion("A1", "Output integrated", "file_exists", ("R1",))]
        ),
    )
    graph = TaskContractGraph(nodes={node.id: node for node in nodes})
    plan = DecompositionPlan(situation, ExecutionShape.GRAPH, graph)
    plan.validate()
    return plan


def _patch_contract(*post_checks: str) -> VerificationContract:
    return VerificationContract(
        deterministic_checks=(
            "changed_paths_within_allowlist",
            "patch_non_empty",
            "requirement_coverage",
            *post_checks,
        ),
        root_contribution="Satisfies R1",
    )


class GraphPatchIntegrationTests(unittest.TestCase):
    def test_exception_after_verification_rolls_back_pending_patch(self) -> None:
        class FailingHook(HookSet):
            def post_verify(self, task, verification):
                raise RuntimeError("audit sink unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            patch_dir = root / "patches"
            patch_dir.mkdir()
            node = TaskNodeContract(
                id="write",
                objective="create output",
                requirement_refs=("R1",),
                write_paths=(repo / "result.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:result.txt"),
                assigned_worker_id="worker-a",
            )
            runtime = DelegationRuntime(
                MemoryStore(root / "memory.sqlite3"), hooks=FailingHook()
            )

            def prepare(active_node, task):
                def runner(**_):
                    patch = patch_dir / "worker.patch"
                    patch.write_text(
                        "--- /dev/null\n+++ b/result.txt\n@@ -0,0 +1 @@\n+ok\n"
                    )
                    return WorkerResult(
                        "success", "ok", [Evidence("result.txt", "ok")],
                        proposed_patch_path=patch, changed_paths=["result.txt"],
                    )
                return PreparedWorker(patch_dir / "out.md", ["fake"], "", runner)

            report = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision("worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            ).execute(_plan(repo, [node]), Task("root", repo=repo))
            self.assertFalse(report.accepted)
            self.assertFalse((report.integration_workspace / "result.txt").exists())

    def test_actual_patch_targets_must_match_worker_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "src").mkdir(parents=True)
            patch_dir = root / "patches"
            patch_dir.mkdir()
            node = TaskNodeContract(
                id="write",
                objective="create output",
                requirement_refs=("R1",),
                write_paths=(repo / "src",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:src/actual.txt"),
                assigned_worker_id="worker-a",
            )
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"))

            def prepare(active_node, task):
                def runner(**_):
                    patch = patch_dir / "worker.patch"
                    patch.write_text(
                        "--- /dev/null\n+++ b/src/actual.txt\n@@ -0,0 +1 @@\n+ok\n"
                    )
                    return WorkerResult(
                        "success", "ok", [Evidence("src/actual.txt", "ok")],
                        proposed_patch_path=patch, changed_paths=["src/claimed.txt"],
                    )
                return PreparedWorker(patch_dir / "out.md", ["fake"], "", runner)

            report = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision("worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            ).execute(_plan(repo, [node]), Task("root", repo=repo))
            self.assertFalse(report.accepted)
            self.assertFalse((report.integration_workspace / "src" / "actual.txt").exists())
            self.assertTrue(any(
                "changed_paths_match_patch" in issue
                for issue in report.node_verifications["write"].issues
            ))

    def test_missing_context_failure_does_not_penalize_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            node = TaskNodeContract(
                id="inspect",
                objective="inspect missing input",
                requirement_refs=("R1",),
                verification=VerificationContract(
                    deterministic_checks=("file_exists:missing.txt",),
                    root_contribution="Satisfies R1",
                ),
                assigned_worker_id="worker-a",
            )
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(
                MemoryStore(root / "memory.sqlite3"), history=history
            )

            def prepare(active_node, task):
                def runner(**_):
                    return WorkerResult("success", "looked", [])
                return PreparedWorker(root / "out.md", ["fake"], "", runner)

            report = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision("worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            ).execute(_plan(repo, [node]), Task("root", repo=repo))
            self.assertFalse(report.accepted)
            self.assertEqual(
                history.outcomes[0].failure_attribution,
                FailureAttribution.MISSING_CONTEXT,
            )

    def test_successor_reads_predecessor_integrated_state_and_source_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "state.txt").write_text("v1\n")
            patch_dir = root / "patches"
            patch_dir.mkdir()
            edit = TaskNodeContract(
                id="edit",
                objective="change state",
                requirement_refs=("R1",),
                allowed_paths=(repo / "state.txt",),
                write_paths=(repo / "state.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:state.txt"),
                assigned_worker_id="worker-a",
            )
            confirm = TaskNodeContract(
                id="confirm",
                objective="read integrated state",
                requirement_refs=("R1",),
                allowed_paths=(repo / "state.txt",),
                verification=VerificationContract(
                    deterministic_checks=("file_exists:state.txt", "requirement_coverage"),
                    root_contribution="Satisfies R1",
                ),
                assigned_worker_id="worker-a",
            )
            seen: list[str] = []
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"), history=history)

            def prepare(node, task):
                def runner(**kwargs):
                    current = kwargs["task"]
                    if node.id == "edit":
                        patch = patch_dir / "edit.patch"
                        patch.write_text(
                            "--- a/state.txt\n+++ b/state.txt\n@@ -1 +1 @@\n-v1\n+v2\n"
                        )
                        return WorkerResult(
                            "success", "edited", [Evidence("edit.evidence", "patch")],
                            proposed_patch_path=patch, changed_paths=["state.txt"],
                        )
                    seen.append((current.repo / "state.txt").read_text())
                    return WorkerResult("success", "confirmed", [Evidence("confirm.evidence", "v2")])

                return PreparedWorker(patch_dir / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision(node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            report = service.execute(_plan(repo, [edit, confirm]), Task("root", repo=repo))

            self.assertTrue(report.accepted, report.to_dict())
            self.assertEqual(seen, ["v2\n"])
            self.assertEqual((report.integration_workspace / "state.txt").read_text(), "v2\n")
            self.assertEqual((repo / "state.txt").read_text(), "v1\n")
            self.assertEqual([item.status for item in history.outcomes], [OutcomeStatus.SUCCESS, OutcomeStatus.SUCCESS])

    def test_post_verifier_failure_rolls_back_then_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            patch_dir = root / "patches"
            patch_dir.mkdir()
            node = TaskNodeContract(
                id="write",
                objective="create valid output",
                requirement_refs=("R1",),
                write_paths=(repo / "result.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_contains:result.txt"),
                max_attempts=2,
                assigned_worker_id="worker-a",
            )
            calls = 0
            workspace_preconditions: list[bool] = []
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"), history=history)

            def prepare(active_node, task):
                def runner(**kwargs):
                    nonlocal calls
                    calls += 1
                    current = kwargs["task"]
                    workspace_preconditions.append((current.repo / "result.txt").exists())
                    value = "bad" if calls == 1 else "good"
                    patch = patch_dir / f"attempt-{calls}.patch"
                    patch.write_text(
                        f"--- /dev/null\n+++ b/result.txt\n@@ -0,0 +1 @@\n+{value}\n"
                    )
                    return WorkerResult(
                        "success",
                        value,
                        [Evidence("result.txt", "good\n")],
                        proposed_patch_path=patch,
                        changed_paths=["result.txt"],
                    )

                return PreparedWorker(patch_dir / "out.md", ["fake"], active_node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision(active_node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            report = service.execute(_plan(repo, [node]), Task("root", repo=repo))

            self.assertTrue(report.accepted, report.to_dict())
            self.assertEqual(workspace_preconditions, [False, False])
            self.assertEqual((report.integration_workspace / "result.txt").read_text(), "good\n")
            self.assertFalse((repo / "result.txt").exists())
            self.assertEqual(report.node_attempts["write"], 2)
            self.assertEqual(report.replan_decisions["write"][0].action.value, "retry_same_worker")
            self.assertEqual([item.status for item in history.outcomes], [OutcomeStatus.FAILED, OutcomeStatus.SUCCESS])

    def test_fallback_worker_is_used_within_attempt_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            patch_dir = root / "patches"
            patch_dir.mkdir()
            node = TaskNodeContract(
                id="write",
                objective="create valid output",
                requirement_refs=("R1",),
                write_paths=(repo / "result.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_contains:result.txt"),
                max_attempts=2,
                assigned_worker_id="worker-a",
            )
            used: list[str] = []
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"))

            def prepare(active_node, task):
                def runner(**_):
                    worker = active_node.assigned_worker_id or "worker-a"
                    used.append(worker)
                    value = "good" if worker == "worker-b" else "bad"
                    patch = patch_dir / f"{worker}.patch"
                    patch.write_text(
                        f"--- /dev/null\n+++ b/result.txt\n@@ -0,0 +1 @@\n+{value}\n"
                    )
                    return WorkerResult(
                        "success", value, [Evidence("result.txt", "good\n")],
                        proposed_patch_path=patch, changed_paths=["result.txt"],
                    )

                return PreparedWorker(patch_dir / "out.md", ["fake"], active_node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision(active_node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                fallback_worker=lambda active_node, attempt: "worker-b",
                integration_parent_dir=root / "graph-runs",
            )
            report = service.execute(_plan(repo, [node]), Task("root", repo=repo))
            self.assertTrue(report.accepted, report.to_dict())
            self.assertEqual(used, ["worker-a", "worker-b"])
            self.assertEqual(report.replan_decisions["write"][0].action.value, "select_another_worker")

    def test_source_version_conflict_blocks_without_penalizing_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "state.txt").write_text("v1\n")
            patch_dir = root / "patches"
            patch_dir.mkdir()
            node = TaskNodeContract(
                id="write",
                objective="update state",
                requirement_refs=("R1",),
                write_paths=(repo / "state.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:state.txt"),
                assigned_worker_id="worker-a",
            )
            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"), history=history)

            def prepare(active_node, task):
                def runner(**_):
                    (repo / "state.txt").write_text("user-change\n")
                    patch = patch_dir / "worker.patch"
                    patch.write_text(
                        "--- a/state.txt\n+++ b/state.txt\n@@ -1 +1 @@\n-v1\n+worker-change\n"
                    )
                    return WorkerResult(
                        "success", "changed", [Evidence("state.txt", "worker")],
                        proposed_patch_path=patch, changed_paths=["state.txt"],
                    )

                return PreparedWorker(patch_dir / "out.md", ["fake"], active_node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda active_node, task: _decision("worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            report = service.execute(_plan(repo, [node]), Task("root", repo=repo))
            self.assertFalse(report.accepted)
            self.assertEqual(
                history.outcomes[0].failure_attribution,
                FailureAttribution.INTEGRATION_CONFLICT,
            )
            self.assertEqual((report.integration_workspace / "state.txt").read_text(), "v1\n")
            self.assertEqual((repo / "state.txt").read_text(), "user-change\n")


# ---------------------------------------------------------------------------
# Parallel integration tests
# ---------------------------------------------------------------------------

class TestParallelGraphPatchIntegration(unittest.TestCase):
    """Integration tests for bounded parallel graph execution."""

    def test_parallel_independent_patches_both_applied(self) -> None:
        """Two independent PATCH nodes with disjoint writes both succeed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "a.txt").write_text("old-a\n")
            (repo / "b.txt").write_text("old-b\n")
            patch_dir = root / "patches"
            patch_dir.mkdir()

            node_a = TaskNodeContract(
                id="patch-a",
                objective="update a.txt",
                requirement_refs=("R1",),
                allowed_paths=(repo / "a.txt",),
                write_paths=(repo / "a.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:a.txt"),
                assigned_worker_id="worker-a",
            )
            node_b = TaskNodeContract(
                id="patch-b",
                objective="update b.txt",
                requirement_refs=("R1",),
                allowed_paths=(repo / "b.txt",),
                write_paths=(repo / "b.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:b.txt"),
                assigned_worker_id="worker-b",
            )

            history = InMemoryHistoryRepository()
            runtime = DelegationRuntime(
                MemoryStore(root / "memory.sqlite3"), history=history
            )

            def prepare(node, task):
                def runner(**_):
                    if node.id == "patch-a":
                        patch = patch_dir / "a.patch"
                        patch.write_text(
                            "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old-a\n+new-a\n"
                        )
                        return WorkerResult(
                            "success", "updated a", [Evidence("a.txt", "new-a")],
                            proposed_patch_path=patch, changed_paths=["a.txt"],
                        )
                    else:
                        patch = patch_dir / "b.patch"
                        patch.write_text(
                            "--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-old-b\n+new-b\n"
                        )
                        return WorkerResult(
                            "success", "updated b", [Evidence("b.txt", "new-b")],
                            proposed_patch_path=patch, changed_paths=["b.txt"],
                        )

                return PreparedWorker(patch_dir / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision(node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            plan = _independent_plan(repo, [node_a, node_b])
            report = service.execute(
                plan, Task("root", repo=repo), max_parallel=2,
            )

            self.assertTrue(report.accepted, report.to_dict())
            ws = report.integration_workspace
            self.assertEqual((ws / "a.txt").read_text(), "new-a\n")
            self.assertEqual((ws / "b.txt").read_text(), "new-b\n")
            # Source repo unchanged
            self.assertEqual((repo / "a.txt").read_text(), "old-a\n")
            self.assertEqual((repo / "b.txt").read_text(), "old-b\n")
            self.assertEqual(len(report.graph_result.execution_order), 2)

    def test_overlapping_write_paths_force_serialization(self) -> None:
        """Overlapping writes serialize, then RootVerifier flags ambiguous ownership."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "shared.txt").write_text("v0\n")
            patch_dir = root / "patches"
            patch_dir.mkdir()

            node_a = TaskNodeContract(
                id="writer-a",
                objective="write first",
                requirement_refs=("R1",),
                allowed_paths=(repo / "shared.txt",),
                write_paths=(repo / "shared.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:shared.txt"),
                assigned_worker_id="worker-a",
            )
            node_b = TaskNodeContract(
                id="writer-b",
                objective="write second",
                requirement_refs=("R1",),
                allowed_paths=(repo / "shared.txt",),
                write_paths=(repo / "shared.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:shared.txt"),
                assigned_worker_id="worker-b",
            )

            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"))

            def prepare(node, task):
                def runner(**_):
                    if node.id == "writer-a":
                        patch = patch_dir / "a.patch"
                        patch.write_text(
                            "--- a/shared.txt\n+++ b/shared.txt\n@@ -1 +1 @@\n-v0\n+from-a\n"
                        )
                        return WorkerResult(
                            "success", "a", [Evidence("shared.txt", "from-a")],
                            proposed_patch_path=patch, changed_paths=["shared.txt"],
                        )
                    else:
                        patch = patch_dir / "b.patch"
                        patch.write_text(
                            "--- a/shared.txt\n+++ b/shared.txt\n@@ -1 +1 @@\n-from-a\n+from-b\n"
                        )
                        return WorkerResult(
                            "success", "b", [Evidence("shared.txt", "from-b")],
                            proposed_patch_path=patch, changed_paths=["shared.txt"],
                        )

                return PreparedWorker(patch_dir / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision(node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            plan = _independent_plan(repo, [node_a, node_b])
            report = service.execute(
                plan, Task("root", repo=repo), max_parallel=2,
            )

            # Both should succeed, serialized: writer-a first (lexicographic), then writer-b.
            self.assertTrue(report.graph_result.all_succeeded, report.to_dict())
            self.assertFalse(report.accepted)
            self.assertTrue(
                any("Artifact conflicts detected" in issue for issue in report.root_verification.issues)
            )
            ws = report.integration_workspace
            self.assertEqual((ws / "shared.txt").read_text(), "from-b\n")

    def test_successor_sees_predecessor_changes_with_parallel(self) -> None:
        """Even with max_parallel > 1, a successor sees committed predecessor state."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "data.txt").write_text("initial\n")
            patch_dir = root / "patches"
            patch_dir.mkdir()

            edit = TaskNodeContract(
                id="edit",
                objective="modify data",
                requirement_refs=("R1",),
                allowed_paths=(repo / "data.txt",),
                write_paths=(repo / "data.txt",),
                execution_mode=ExecutionMode.PATCH,
                verification=_patch_contract("file_exists:data.txt"),
                assigned_worker_id="worker-a",
            )
            read = TaskNodeContract(
                id="read",
                objective="verify data",
                requirement_refs=("R1",),
                allowed_paths=(repo / "data.txt",),
                verification=VerificationContract(
                    deterministic_checks=("file_exists:data.txt", "requirement_coverage"),
                    root_contribution="Satisfies R1",
                ),
                assigned_worker_id="worker-a",
            )

            seen: list[str] = []
            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"))

            def prepare(node, task):
                def runner(**kwargs):
                    if node.id == "edit":
                        patch = patch_dir / "edit.patch"
                        patch.write_text(
                            "--- a/data.txt\n+++ b/data.txt\n@@ -1 +1 @@\n-initial\n+modified\n"
                        )
                        return WorkerResult(
                            "success", "edited", [Evidence("edit.evidence", "ok")],
                            proposed_patch_path=patch, changed_paths=["data.txt"],
                        )
                    current = kwargs["task"]
                    seen.append((current.repo / "data.txt").read_text())
                    return WorkerResult("success", "confirmed", [Evidence("read.evidence", "ok")])

                return PreparedWorker(patch_dir / f"{node.id}.md", ["fake"], node.objective, runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision(node.assigned_worker_id or "worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            plan = _plan(repo, [edit, read])
            report = service.execute(
                plan, Task("root", repo=repo), max_parallel=2,
            )

            self.assertTrue(report.accepted, report.to_dict())
            self.assertEqual(seen, ["modified\n"])

    def test_parallel_dry_run_reports_planned_order(self) -> None:
        """Dry-run with max_parallel > 1 produces valid execution order."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()

            node_a = TaskNodeContract(
                id="a",
                objective="task a",
                requirement_refs=("R1",),
                verification=VerificationContract(
                    deterministic_checks=("requirement_coverage",),
                    root_contribution="Satisfies R1",
                ),
                assigned_worker_id="worker-a",
            )
            node_b = TaskNodeContract(
                id="b",
                objective="task b",
                requirement_refs=("R1",),
                verification=VerificationContract(
                    deterministic_checks=("requirement_coverage",),
                    root_contribution="Satisfies R1",
                ),
                assigned_worker_id="worker-b",
            )

            runtime = DelegationRuntime(MemoryStore(root / "memory.sqlite3"))

            def prepare(node, task):
                def runner(**_):
                    return WorkerResult("success", "done", [])
                return PreparedWorker(root / "out.md", ["fake"], "", runner)

            service = GraphExecutionService(
                runtime,
                decide=lambda node, task: _decision("worker-a"),
                prepare=prepare,
                integration_parent_dir=root / "graph-runs",
            )
            plan = _independent_plan(repo, [node_a, node_b])
            report = service.execute(
                plan, Task("root", repo=repo), execute=False, max_parallel=2,
            )

            self.assertTrue(report.graph_result.all_succeeded)
            self.assertEqual(len(report.graph_result.execution_order), 2)
            self.assertIsNone(report.integration_workspace)


if __name__ == "__main__":
    unittest.main()
