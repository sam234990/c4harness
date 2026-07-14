"""Tests for task-contract graph execution (sequential and parallel).

Covers:
* Execution order (linear chain respects dependency order).
* Independent ready nodes (lexicographic tie-breaking).
* Failure blocking (downstream nodes are BLOCKED when a required dep fails).
* Empty graph (no nodes → terminal, no crash).
* Cyclic graph (rejected at graph-construction time by ``TaskContractGraph``).
* Incomplete / deadlock detection (terminal but not all_succeeded and no failures).
* Dry-run semantics (execute=False skips runner, still walks nodes).
* Stable output (re-running produces identical execution order and outcomes).
* Exception handling (runner exception → node FAILED, downstream BLOCKED).
* Multi-branch diamond dependency.
* **Parallel** – independent nodes with disjoint write paths run in one batch.
* **Parallel** – overlapping write-path nodes are serialized deterministically.
* **Parallel** – failure propagation when a node in a parallel batch fails.
* **Parallel** – max_parallel < 1 is rejected.
* **Parallel** – dependency ordering is respected even with max_parallel > 1.
* **Parallel** – dry-run with max_parallel > 1 still walks all nodes.
* **Parallel** – deterministic output with bounded parallelism.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from c4harness.core.graph import (
    ExecutionMode,
    GraphEdge,
    TaskContractGraph,
    TaskNodeContract,
)
from c4harness.decompose import VerificationContract

# Under test — adjust import paths if the package layout differs.
from c4harness.application.run_graph import NodeResult, RunGraph
from c4harness.delegator.scheduler import (
    GraphScheduler,
    NodeState,
    select_parallel_batch,
    _nodes_have_overlapping_writes,
    _write_paths_overlap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id: str, objective: str = "") -> TaskNodeContract:
    """Create a minimal verifiable node for testing."""
    return TaskNodeContract(
        id=node_id,
        objective=objective or f"objective for {node_id}",
        verification=VerificationContract(evidence_requirements=("evidence",)),
    )


def _make_write_node(
    node_id: str,
    write_paths: list[str],
    objective: str = "",
) -> TaskNodeContract:
    """Create a minimal verifiable PATCH node with declared write paths."""
    return TaskNodeContract(
        id=node_id,
        objective=objective or f"objective for {node_id}",
        write_paths=tuple(Path(p) for p in write_paths),
        execution_mode=ExecutionMode.PATCH,
        verification=VerificationContract(evidence_requirements=("evidence",)),
    )


def _build_graph(
    nodes: list[str],
    edges: list[tuple[str, str]] | None = None,
) -> TaskContractGraph:
    """Build a ``TaskContractGraph`` from node ids and (source, target) edges."""
    graph = TaskContractGraph()
    for nid in nodes:
        graph.add_node(_make_node(nid))
    for source, target in edges or []:
        graph.add_edge(GraphEdge(source=source, target=target))
    return graph


def _ok_runner(results: dict[str, Any] | None = None) -> Any:
    """Return a runner that always succeeds, optionally with per-node results."""
    results = results or {}

    def _run(node: TaskNodeContract) -> NodeResult:
        return NodeResult(success=True, result=results.get(node.id))

    return _run


def _fail_runner(fail_ids: set[str]) -> Any:
    """Return a runner that fails for nodes whose id is in *fail_ids*."""
    def _run(node: TaskNodeContract) -> NodeResult:
        if node.id in fail_ids:
            return NodeResult(success=False, error=f"{node.id} intentionally failed")
        return NodeResult(success=True)

    return _run


def _raising_runner(raise_ids: set[str]) -> Any:
    """Return a runner that raises for nodes whose id is in *raise_ids*."""
    def _run(node: TaskNodeContract) -> NodeResult:
        if node.id in raise_ids:
            raise RuntimeError(f"backend exploded for {node.id}")
        return NodeResult(success=True)

    return _run


# ---------------------------------------------------------------------------
# Tests — sequential (existing)
# ---------------------------------------------------------------------------

class TestExecutionOrder(unittest.TestCase):
    """Linear chain: A → B → C must execute in order A, B, C."""

    def test_linear_chain_respects_dependency_order(self) -> None:
        graph = _build_graph(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result.execution_order, ["A", "B", "C"])
        self.assertTrue(result.all_succeeded)
        self.assertTrue(result.is_terminal)
        self.assertFalse(result.has_failures)


class TestIndependentReadyNodes(unittest.TestCase):
    """Independent nodes with no edges execute in lexicographic order."""

    def test_independent_nodes_lexicographic_order(self) -> None:
        graph = _build_graph(["C", "A", "B"])
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result.execution_order, ["A", "B", "C"])
        self.assertTrue(result.all_succeeded)

    def test_ready_at_same_level_sorted(self) -> None:
        # Diamond: A → B, A → C, B → D, C → D
        # B and C are both ready after A; must be sorted.
        graph = _build_graph(
            ["A", "B", "C", "D"],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        result = RunGraph(graph, runner=_ok_runner()).execute()
        # After A, B and C are ready. Lexicographic: B before C.
        self.assertEqual(result.execution_order, ["A", "B", "C", "D"])
        self.assertTrue(result.all_succeeded)


class TestFailureBlocking(unittest.TestCase):
    """When a required dependency fails, downstream nodes are BLOCKED."""

    def test_failure_blocks_direct_dependent(self) -> None:
        graph = _build_graph(["A", "B"], [("A", "B")])
        result = RunGraph(graph, runner=_fail_runner({"A"})).execute()
        self.assertEqual(result.execution_order, ["A"])
        self.assertEqual(result.node_outcomes["A"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["B"].state, NodeState.BLOCKED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)
        self.assertFalse(result.all_succeeded)

    def test_failure_blocks_transitive_dependents(self) -> None:
        # A → B → C → D; A fails → B, C, D all blocked.
        graph = _build_graph(
            ["A", "B", "C", "D"],
            [("A", "B"), ("B", "C"), ("C", "D")],
        )
        result = RunGraph(graph, runner=_fail_runner({"A"})).execute()
        self.assertEqual(result.execution_order, ["A"])
        self.assertEqual(result.node_outcomes["A"].state, NodeState.FAILED)
        for nid in ("B", "C", "D"):
            self.assertEqual(
                result.node_outcomes[nid].state,
                NodeState.BLOCKED,
                f"{nid} should be BLOCKED",
            )

    def test_failure_in_branch_blocks_only_that_branch(self) -> None:
        # Diamond: A → B, A → C, B → D, C → D
        # B fails → D blocked.  C still succeeds.
        # D depends on both B and C; since B failed, D is blocked.
        graph = _build_graph(
            ["A", "B", "C", "D"],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        result = RunGraph(graph, runner=_fail_runner({"B"})).execute()
        self.assertEqual(result.node_outcomes["A"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["B"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["C"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["D"].state, NodeState.BLOCKED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)

    def test_independent_branch_succeeds_despite_other_failure(self) -> None:
        # Two independent chains: A → B and X → Y.
        # A fails → B blocked.  X → Y still completes.
        graph = _build_graph(
            ["A", "B", "X", "Y"],
            [("A", "B"), ("X", "Y")],
        )
        result = RunGraph(graph, runner=_fail_runner({"A"})).execute()
        self.assertEqual(result.node_outcomes["A"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["B"].state, NodeState.BLOCKED)
        self.assertEqual(result.node_outcomes["X"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["Y"].state, NodeState.SUCCEEDED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)
        self.assertFalse(result.all_succeeded)


class TestEmptyGraph(unittest.TestCase):
    """An empty graph is terminal immediately."""

    def test_empty_graph_no_crash(self) -> None:
        graph = TaskContractGraph()
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result.execution_order, [])
        # With no outcomes, all_succeeded is False (vacuously false guard).
        self.assertFalse(result.all_succeeded)
        self.assertTrue(result.is_terminal)
        self.assertFalse(result.has_failures)


class TestCycleDetection(unittest.TestCase):
    """Cycles are rejected at graph-construction time."""

    def test_cycle_rejected_by_graph(self) -> None:
        graph = _build_graph(["A", "B"], [("A", "B")])
        with self.assertRaisesRegex(ValueError, "acyclic"):
            graph.add_edge(GraphEdge(source="B", target="A"))


class TestDeadlockIncompleteDetection(unittest.TestCase):
    """Terminal graph that is not all_succeeded and has no failures = deadlock."""

    def test_deadlock_when_unreachable_nodes_exist(self) -> None:
        # Manually mark a PENDING node as BLOCKED to simulate unreachable state.
        graph = _build_graph(["A", "B"])
        scheduler = GraphScheduler(graph)
        # Simulate: A ran and succeeded, B is still PENDING but has an
        # unsatisfiable requirement from a non-existent source — we can't
        # actually build that cleanly, so test via scheduler directly.
        scheduler.mark_running("A")
        scheduler.mark_succeeded("A")
        # B has no edges so it should be ready.  Force it to BLOCKED manually
        # to simulate a compile-time missed edge.
        scheduler.mark_blocked("B", "simulated unreachable node")
        result = scheduler.build_result()
        self.assertTrue(result.is_terminal)
        self.assertFalse(result.all_succeeded)
        self.assertFalse(result.has_failures)
        # deadlock_detected: terminal, not all_succeeded, no failures.
        # But B is BLOCKED → is_incomplete is True; deadlock_detected also True
        # because there are no FAILED nodes.
        self.assertTrue(result.deadlock_detected)
        self.assertTrue(result.is_incomplete)

    def test_scheduler_reports_not_terminal_while_running(self) -> None:
        graph = _build_graph(["A"])
        scheduler = GraphScheduler(graph)
        scheduler.mark_running("A")
        self.assertFalse(scheduler.is_terminal())


class TestDryRun(unittest.TestCase):
    """execute=False walks nodes without calling the runner."""

    def test_dry_run_skips_runner(self) -> None:
        call_log: list[str] = []

        def logging_runner(node: TaskNodeContract) -> NodeResult:
            call_log.append(node.id)
            return NodeResult(success=True)

        graph = _build_graph(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = RunGraph(graph, runner=logging_runner).execute(execute=False)
        # Runner should NOT have been called.
        self.assertEqual(call_log, [])
        # But execution order and outcomes should still be populated.
        self.assertEqual(result.execution_order, ["A", "B", "C"])
        self.assertTrue(result.all_succeeded)

    def test_dry_run_respects_dependency_order(self) -> None:
        graph = _build_graph(
            ["A", "B", "C"],
            [("A", "C"), ("B", "C")],
        )
        result = RunGraph(graph).execute(execute=False)
        # A and B are independent; C comes after both.
        self.assertEqual(result.execution_order.index("C"), 2)
        self.assertTrue(result.all_succeeded)


class TestStableOutput(unittest.TestCase):
    """Running the same graph twice produces identical results."""

    def test_deterministic_execution_order(self) -> None:
        graph = _build_graph(
            ["Z", "A", "M", "B"],
            [("A", "M"), ("B", "M")],
        )
        result1 = RunGraph(graph, runner=_ok_runner()).execute()
        result2 = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result1.execution_order, result2.execution_order)
        self.assertEqual(result1.to_dict(), result2.to_dict())


class TestExceptionHandling(unittest.TestCase):
    """Runner exceptions are caught and treated as node failures."""

    def test_exception_marks_node_failed(self) -> None:
        graph = _build_graph(["A", "B"], [("A", "B")])
        result = RunGraph(graph, runner=_raising_runner({"A"})).execute()
        self.assertEqual(result.node_outcomes["A"].state, NodeState.FAILED)
        self.assertIn("RuntimeError", result.node_outcomes["A"].error)
        self.assertEqual(result.node_outcomes["B"].state, NodeState.BLOCKED)

    def test_exception_in_later_node_still_completes_earlier(self) -> None:
        graph = _build_graph(["A", "B"], [("A", "B")])
        result = RunGraph(graph, runner=_raising_runner({"B"})).execute()
        self.assertEqual(result.node_outcomes["A"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["B"].state, NodeState.FAILED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)


class TestSchedulerStateTransitions(unittest.TestCase):
    """Direct tests for the GraphScheduler state machine."""

    def test_mark_running_rejects_non_pending(self) -> None:
        graph = _build_graph(["A"])
        scheduler = GraphScheduler(graph)
        scheduler.mark_running("A")
        with self.assertRaisesRegex(ValueError, "Cannot mark A as running"):
            scheduler.mark_running("A")

    def test_mark_succeeded_rejects_non_running(self) -> None:
        graph = _build_graph(["A"])
        scheduler = GraphScheduler(graph)
        with self.assertRaisesRegex(ValueError, "Cannot mark A as succeeded"):
            scheduler.mark_succeeded("A")

    def test_mark_failed_rejects_non_running(self) -> None:
        graph = _build_graph(["A"])
        scheduler = GraphScheduler(graph)
        with self.assertRaisesRegex(ValueError, "Cannot mark A as failed"):
            scheduler.mark_failed("A")

    def test_ready_nodes_empty_when_all_done(self) -> None:
        graph = _build_graph(["A"])
        scheduler = GraphScheduler(graph)
        scheduler.mark_running("A")
        scheduler.mark_succeeded("A")
        self.assertEqual(scheduler.ready_nodes(), [])
        self.assertTrue(scheduler.is_terminal())


class TestGraphResultToDict(unittest.TestCase):
    """Verify the serialisable output structure."""

    def test_to_dict_structure(self) -> None:
        graph = _build_graph(["A", "B"], [("A", "B")])
        result = RunGraph(graph, runner=_ok_runner()).execute()
        d = result.to_dict()
        self.assertIn("execution_order", d)
        self.assertIn("node_outcomes", d)
        self.assertIn("all_succeeded", d)
        self.assertIn("has_failures", d)
        self.assertIn("is_terminal", d)
        self.assertIn("deadlock_detected", d)
        self.assertIn("is_incomplete", d)
        self.assertTrue(d["all_succeeded"])
        self.assertFalse(d["has_failures"])
        self.assertTrue(d["is_terminal"])
        self.assertFalse(d["deadlock_detected"])
        self.assertFalse(d["is_incomplete"])


class TestNodeResultDataclass(unittest.TestCase):
    """NodeResult round-trip."""

    def test_node_result_fields(self) -> None:
        r = NodeResult(success=True, error="none", result={"key": "value"})
        self.assertTrue(r.success)
        self.assertEqual(r.error, "none")
        self.assertEqual(r.result, {"key": "value"})


class TestSingleRootNode(unittest.TestCase):
    """A single root contract node (no edges) runs and succeeds."""

    def test_single_root_node(self) -> None:
        graph = _build_graph(["root_contract"])
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result.execution_order, ["root_contract"])
        self.assertTrue(result.all_succeeded)


class TestLargeFanOut(unittest.TestCase):
    """Many independent nodes fan out from one root."""

    def test_fan_out_all_succeed(self) -> None:
        node_ids = [f"n{i}" for i in range(20)]
        edges = [("root", nid) for nid in node_ids]
        graph = _build_graph(["root"] + node_ids, edges)
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertEqual(result.node_outcomes["root"].state, NodeState.SUCCEEDED)
        for nid in node_ids:
            self.assertEqual(result.node_outcomes[nid].state, NodeState.SUCCEEDED)
        self.assertTrue(result.all_succeeded)
        # root must be first
        self.assertEqual(result.execution_order[0], "root")

    def test_fan_out_root_failure_blocks_all(self) -> None:
        node_ids = [f"n{i}" for i in range(20)]
        edges = [("root", nid) for nid in node_ids]
        graph = _build_graph(["root"] + node_ids, edges)
        result = RunGraph(graph, runner=_fail_runner({"root"})).execute()
        self.assertEqual(result.node_outcomes["root"].state, NodeState.FAILED)
        for nid in node_ids:
            self.assertEqual(result.node_outcomes[nid].state, NodeState.BLOCKED)


# ---------------------------------------------------------------------------
# Write-path overlap helpers (unit tests for the scheduler helpers)
# ---------------------------------------------------------------------------

class TestWritePathOverlap(unittest.TestCase):
    """Low-level tests for _write_paths_overlap."""

    def test_same_path_overlaps(self) -> None:
        self.assertTrue(_write_paths_overlap("src/main.py", "src/main.py"))

    def test_ancestor_overlaps_descendant(self) -> None:
        self.assertTrue(_write_paths_overlap("src", "src/main.py"))
        self.assertTrue(_write_paths_overlap("src/main.py", "src"))

    def test_sibling_files_do_not_overlap(self) -> None:
        self.assertFalse(_write_paths_overlap("src/a.py", "src/b.py"))

    def test_sibling_dirs_do_not_overlap(self) -> None:
        self.assertFalse(_write_paths_overlap("lib", "src"))

    def test_deeply_nested_overlap(self) -> None:
        self.assertTrue(_write_paths_overlap("a/b/c", "a/b/c/d/e"))

    def test_prefix_component_mismatch(self) -> None:
        # "src2" is NOT a prefix of "src/main.py" (component-aware).
        self.assertFalse(_write_paths_overlap("src2", "src/main.py"))


class TestNodesHaveOverlappingWrites(unittest.TestCase):
    """Test the node-level overlap check."""

    def test_no_write_paths_never_overlap(self) -> None:
        a = _make_node("a")
        b = _make_node("b")
        self.assertFalse(_nodes_have_overlapping_writes(a, b))

    def test_disjoint_writes_no_overlap(self) -> None:
        a = _make_write_node("a", ["src/a.py"])
        b = _make_write_node("b", ["src/b.py"])
        self.assertFalse(_nodes_have_overlapping_writes(a, b))

    def test_same_write_path_overlaps(self) -> None:
        a = _make_write_node("a", ["src/main.py"])
        b = _make_write_node("b", ["src/main.py"])
        self.assertTrue(_nodes_have_overlapping_writes(a, b))

    def test_ancestor_directory_overlaps(self) -> None:
        a = _make_write_node("a", ["src"])
        b = _make_write_node("b", ["src/main.py"])
        self.assertTrue(_nodes_have_overlapping_writes(a, b))

    def test_read_only_node_never_conflicts(self) -> None:
        read_only = _make_node("ro")
        writer = _make_write_node("w", ["src/main.py"])
        self.assertFalse(_nodes_have_overlapping_writes(read_only, writer))


class TestSelectParallelBatch(unittest.TestCase):
    """Test the greedy batch selection algorithm."""

    def test_empty_input(self) -> None:
        self.assertEqual(select_parallel_batch([], 4), [])

    def test_single_node(self) -> None:
        node = _make_node("a")
        batch = select_parallel_batch([node], 4)
        self.assertEqual(len(batch), 1)

    def test_non_overlapping_nodes_all_selected(self) -> None:
        a = _make_write_node("a", ["src/a.py"])
        b = _make_write_node("b", ["src/b.py"])
        c = _make_write_node("c", ["lib/c.py"])
        batch = select_parallel_batch([a, b, c], 4)
        self.assertEqual(len(batch), 3)
        # Deterministic: order matches input
        self.assertEqual([n.id for n in batch], ["a", "b", "c"])

    def test_overlapping_nodes_limited(self) -> None:
        a = _make_write_node("a", ["src/main.py"])
        b = _make_write_node("b", ["src/main.py"])
        batch = select_parallel_batch([a, b], 4)
        # Only the first should be selected
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0].id, "a")

    def test_max_parallel_limits_batch_size(self) -> None:
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        c = _make_write_node("c", ["c.py"])
        batch = select_parallel_batch([a, b, c], 2)
        self.assertEqual(len(batch), 2)
        self.assertEqual([n.id for n in batch], ["a", "b"])

    def test_mixed_overlap_and_disjoint(self) -> None:
        a = _make_write_node("a", ["src/main.py"])
        b = _make_write_node("b", ["lib/utils.py"])
        c = _make_write_node("c", ["src/main.py"])  # overlaps a
        batch = select_parallel_batch([a, b, c], 4)
        # a selected first, b doesn't overlap → selected, c overlaps a → skipped
        self.assertEqual([n.id for n in batch], ["a", "b"])

    def test_read_only_nodes_always_compatible(self) -> None:
        a = _make_node("a")
        b = _make_node("b")
        c = _make_write_node("c", ["src/x.py"])
        batch = select_parallel_batch([a, b, c], 4)
        self.assertEqual(len(batch), 3)

    def test_max_parallel_must_be_at_least_one(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_parallel must be at least 1"):
            select_parallel_batch([], 0)


# ---------------------------------------------------------------------------
# Tests — parallel execution
# ---------------------------------------------------------------------------

class TestParallelIndependentNodes(unittest.TestCase):
    """Independent nodes with disjoint write paths run in parallel."""

    def test_independent_non_overlapping_parallel(self) -> None:
        # Two independent nodes with different write paths.
        a = _make_write_node("a", ["src/a.py"])
        b = _make_write_node("b", ["src/b.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertTrue(result.all_succeeded)
        self.assertEqual(result.execution_order, ["a", "b"])

    def test_parallel_still_respects_max(self) -> None:
        # Three independent non-overlapping nodes, max_parallel=2.
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        c = _make_write_node("c", ["c.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b, "c": c})
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertTrue(result.all_succeeded)
        # All three should eventually succeed.
        self.assertEqual(result.node_outcomes["a"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["b"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["c"].state, NodeState.SUCCEEDED)

    def test_parallel_with_read_only_nodes(self) -> None:
        # Read-only nodes (no write paths) are always compatible.
        a = _make_node("a")
        b = _make_node("b")
        c = _make_node("c")
        graph = TaskContractGraph(nodes={"a": a, "b": b, "c": c})
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=3).execute()
        self.assertTrue(result.all_succeeded)
        self.assertEqual(result.execution_order, ["a", "b", "c"])


class TestOverlappingWritePathsSerialized(unittest.TestCase):
    """Nodes with overlapping write paths are serialized."""

    def test_same_write_path_serialized(self) -> None:
        a = _make_write_node("a", ["src/main.py"])
        b = _make_write_node("b", ["src/main.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        # max_parallel=2 but write paths overlap → serialized
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertTrue(result.all_succeeded)
        # a runs first (lexicographic), b must wait
        self.assertEqual(result.execution_order, ["a", "b"])

    def test_ancestor_directory_serialized(self) -> None:
        a = _make_write_node("a", ["src"])
        b = _make_write_node("b", ["src/main.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertTrue(result.all_succeeded)
        self.assertEqual(result.execution_order, ["a", "b"])

    def test_disjoint_writes_run_together(self) -> None:
        a = _make_write_node("a", ["src/a.py"])
        b = _make_write_node("b", ["lib/b.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertTrue(result.all_succeeded)
        # Both in same batch, order is lexicographic
        self.assertEqual(result.execution_order, ["a", "b"])


class TestParallelFailurePropagation(unittest.TestCase):
    """Failure in a parallel batch correctly blocks dependents."""

    def test_failure_in_batch_blocks_downstream(self) -> None:
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        c = _make_node("c")  # depends on a
        graph = TaskContractGraph(nodes={"a": a, "b": b, "c": c})
        graph.add_edge(GraphEdge(source="a", target="c"))
        result = RunGraph(
            graph, runner=_fail_runner({"a"}), max_parallel=2
        ).execute()
        self.assertEqual(result.node_outcomes["a"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["b"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["c"].state, NodeState.BLOCKED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)

    def test_independent_branch_succeeds_despite_failure_with_parallel(self) -> None:
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])  # depends on a
        x = _make_write_node("x", ["x.py"])
        y = _make_write_node("y", ["y.py"])  # depends on x
        graph = TaskContractGraph(nodes={"a": a, "b": b, "x": x, "y": y})
        graph.add_edge(GraphEdge(source="a", target="b"))
        graph.add_edge(GraphEdge(source="x", target="y"))
        result = RunGraph(
            graph, runner=_fail_runner({"a"}), max_parallel=4
        ).execute()
        self.assertEqual(result.node_outcomes["a"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["b"].state, NodeState.BLOCKED)
        self.assertEqual(result.node_outcomes["x"].state, NodeState.SUCCEEDED)
        self.assertEqual(result.node_outcomes["y"].state, NodeState.SUCCEEDED)


class TestMaxParallelValidation(unittest.TestCase):
    """max_parallel must be at least 1."""

    def test_max_parallel_zero_rejected(self) -> None:
        graph = _build_graph(["A"])
        with self.assertRaisesRegex(ValueError, "max_parallel must be at least 1"):
            RunGraph(graph, max_parallel=0)

    def test_max_parallel_negative_rejected(self) -> None:
        graph = _build_graph(["A"])
        with self.assertRaisesRegex(ValueError, "max_parallel must be at least 1"):
            RunGraph(graph, max_parallel=-1)

    def test_max_parallel_one_is_default(self) -> None:
        graph = _build_graph(["A"])
        # Should not raise
        result = RunGraph(graph, runner=_ok_runner()).execute()
        self.assertTrue(result.all_succeeded)


class TestParallelDependencyOrder(unittest.TestCase):
    """Dependencies are respected even with max_parallel > 1."""

    def test_linear_chain_with_parallel(self) -> None:
        graph = _build_graph(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=3).execute()
        self.assertEqual(result.execution_order, ["A", "B", "C"])
        self.assertTrue(result.all_succeeded)

    def test_diamond_with_parallel(self) -> None:
        graph = _build_graph(
            ["A", "B", "C", "D"],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        result = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        # A first, then B and C (parallel), then D
        self.assertEqual(result.execution_order[0], "A")
        self.assertEqual(result.execution_order[-1], "D")
        self.assertIn("B", result.execution_order[1:3])
        self.assertIn("C", result.execution_order[1:3])
        self.assertTrue(result.all_succeeded)


class TestParallelDryRun(unittest.TestCase):
    """Dry-run with max_parallel > 1 still walks all nodes."""

    def test_dry_run_with_parallel(self) -> None:
        call_log: list[str] = []

        def logging_runner(node: TaskNodeContract) -> NodeResult:
            call_log.append(node.id)
            return NodeResult(success=True)

        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        result = RunGraph(
            graph, runner=logging_runner, max_parallel=2
        ).execute(execute=False)
        self.assertEqual(call_log, [])
        self.assertTrue(result.all_succeeded)
        self.assertEqual(result.execution_order, ["a", "b"])


class TestParallelDeterministicOutput(unittest.TestCase):
    """Same graph + same max_parallel → identical execution order."""

    def test_deterministic_with_parallel(self) -> None:
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        c = _make_write_node("c", ["c.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b, "c": c})
        result1 = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        result2 = RunGraph(graph, runner=_ok_runner(), max_parallel=2).execute()
        self.assertEqual(result1.execution_order, result2.execution_order)
        self.assertEqual(result1.to_dict(), result2.to_dict())


class TestParallelExceptionHandling(unittest.TestCase):
    """Exceptions in parallel execution are handled correctly."""

    def test_exception_in_parallel_batch(self) -> None:
        a = _make_write_node("a", ["a.py"])
        b = _make_write_node("b", ["b.py"])
        graph = TaskContractGraph(nodes={"a": a, "b": b})
        result = RunGraph(
            graph, runner=_raising_runner({"a"}), max_parallel=2
        ).execute()
        self.assertEqual(result.node_outcomes["a"].state, NodeState.FAILED)
        self.assertEqual(result.node_outcomes["b"].state, NodeState.SUCCEEDED)
        self.assertTrue(result.has_failures)
        self.assertTrue(result.is_terminal)


if __name__ == "__main__":
    unittest.main()
