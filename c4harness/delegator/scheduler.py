"""Dependency-aware scheduling primitives for task contract graphs.

The scheduler is a pure, deterministic component that operates on a
``TaskContractGraph`` and a map of node states.  It never invokes a worker
backend; that responsibility belongs to the application layer.

Design decisions
================
* **NodeState** – explicit five-state enum: ``PENDING``, ``RUNNING``,
  ``SUCCEEDED``, ``FAILED``, ``BLOCKED``.  ``BLOCKED`` is recorded when all
  upstream required dependencies have not yet succeeded (specifically, when
  at least one required dependency has failed, the downstream node is
  permanently blocked).
* **Ready-node selection** – a node is *ready* when it is ``PENDING`` and
  every ``requires``-edge source is ``SUCCEEDED``.  Ties are broken by
  lexicographic ``node.id`` for determinism.
* **Blocking propagation** – when a required dependency finishes with
  ``FAILED``, every downstream transitive dependent is immediately marked
  ``BLOCKED`` so the runner never attempts it.
* **Terminal-state detection** – the graph is *terminal* when no node is
  ``PENDING`` or ``RUNNING``.  ``GraphResult`` exposes helpers for
  ``all_succeeded``, ``has_failures``, ``deadlock_detected`` (terminal but
  not all_succeeded and no explicit failures — indicates a cycle that was
  not caught at compile time or an incomplete graph), and
  ``is_incomplete`` (terminal, not all succeeded, with at least one
  ``BLOCKED`` node).
* **Dry-run** – the scheduler itself is always "dry"; ``execute=False``
  semantics live in ``run_graph`` which skips calling the runner but still
  records the planned execution order.
* **Parallel-safe batch selection** – ``select_parallel_batch`` returns up
  to *max_parallel* ready nodes whose declared write sets do not overlap
  by equality or ancestor/descendant path prefix.  Nodes with overlapping
  write paths are serialized with deterministic lexicographic selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from ..core.graph import TaskContractGraph, TaskNodeContract


# ---------------------------------------------------------------------------
# Node state
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    """Execution state of a single task-contract node."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Per-node outcome
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class NodeOutcome:
    """Mutable record attached to each node during graph execution."""

    node_id: str
    state: NodeState = NodeState.PENDING
    error: str | None = None
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "node_id": self.node_id,
            "state": self.state.value,
        }
        if self.error is not None:
            data["error"] = self.error
        if self.result is not None:
            data["result"] = self.result
        return data


# ---------------------------------------------------------------------------
# Graph result
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GraphResult:
    """Inspectable result of an entire graph execution run."""

    node_outcomes: dict[str, NodeOutcome] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)

    # -- terminal-state queries ------------------------------------------------

    @property
    def all_succeeded(self) -> bool:
        return bool(self.node_outcomes) and all(
            o.state == NodeState.SUCCEEDED for o in self.node_outcomes.values()
        )

    @property
    def has_failures(self) -> bool:
        return any(o.state == NodeState.FAILED for o in self.node_outcomes.values())

    @property
    def is_terminal(self) -> bool:
        return all(
            o.state in (NodeState.SUCCEEDED, NodeState.FAILED, NodeState.BLOCKED)
            for o in self.node_outcomes.values()
        )

    @property
    def deadlock_detected(self) -> bool:
        """Terminal, not all succeeded, no explicit failures.

        This signals that some nodes remain ``PENDING`` or ``BLOCKED`` in a
        way that cannot progress — typically an unresolvable cycle or a
        graph that was incomplete at compile time.
        """
        if not self.node_outcomes or not self.is_terminal:
            return False
        return not self.all_succeeded and not self.has_failures

    @property
    def is_incomplete(self) -> bool:
        """Terminal with at least one ``BLOCKED`` node."""
        return self.is_terminal and any(
            o.state == NodeState.BLOCKED for o in self.node_outcomes.values()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_order": list(self.execution_order),
            "node_outcomes": {
                nid: o.to_dict() for nid, o in self.node_outcomes.items()
            },
            "all_succeeded": self.all_succeeded,
            "has_failures": self.has_failures,
            "is_terminal": self.is_terminal,
            "deadlock_detected": self.deadlock_detected,
            "is_incomplete": self.is_incomplete,
        }


# ---------------------------------------------------------------------------
# Write-path overlap detection
# ---------------------------------------------------------------------------

def _write_paths_overlap(left: str, right: str) -> bool:
    """Component-aware equality/ancestor/descendant overlap.

    ``src/a.py`` overlaps ``src/a.py`` (equality) and ``src`` (ancestor),
    but does NOT overlap ``src/b.py`` (sibling).
    """
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shorter = min(len(left_parts), len(right_parts))
    return left_parts[:shorter] == right_parts[:shorter]


def _node_write_path_strings(
    node: TaskNodeContract,
    repo: Path | None = None,
) -> list[str]:
    """Extract normalised repo-relative write-path strings from a node."""
    result: list[str] = []
    for path in node.write_paths:
        candidate = path if isinstance(path, Path) else Path(str(path))
        if repo is not None and candidate.is_absolute():
            try:
                candidate = candidate.resolve().relative_to(repo.resolve())
            except ValueError:
                # An out-of-repo write path will be rejected by contract/path
                # validation.  Preserve it here so it cannot alias a valid
                # repo-relative path accidentally.
                pass
        result.append(candidate.as_posix())
    return result


def _nodes_have_overlapping_writes(
    a: TaskNodeContract,
    b: TaskNodeContract,
    repo: Path | None = None,
) -> bool:
    """Return ``True`` if two nodes share any write path by overlap rules."""
    a_paths = _node_write_path_strings(a, repo)
    b_paths = _node_write_path_strings(b, repo)
    for ap in a_paths:
        for bp in b_paths:
            if _write_paths_overlap(ap, bp):
                return True
    return False


def select_parallel_batch(
    ready: list[TaskNodeContract],
    max_parallel: int,
    *,
    repo: Path | None = None,
) -> list[TaskNodeContract]:
    """Select up to *max_parallel* nodes whose write sets do not overlap.

    Uses greedy first-fit over lexicographically sorted *ready* nodes for
    determinism.  A node with no write paths (read-only) never conflicts.
    """
    if max_parallel < 1:
        raise ValueError("max_parallel must be at least 1")
    batch: list[TaskNodeContract] = []
    for node in ready:
        if len(batch) >= max_parallel:
            break
        if not any(_nodes_have_overlapping_writes(node, ex, repo) for ex in batch):
            batch.append(node)
    return batch


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class GraphScheduler:
    """Deterministic dependency scheduler for ``TaskContractGraph``.

    The scheduler does **not** invoke any worker; it only resolves
    dependency order and propagates blocked states.  The application layer
    is responsible for calling the node runner and reporting outcomes back
    via :meth:`mark_succeeded` / :meth:`mark_failed`.
    """

    def __init__(self, graph: TaskContractGraph) -> None:
        self._graph = graph
        self._outcomes: dict[str, NodeOutcome] = {
            nid: NodeOutcome(node_id=nid) for nid in graph.nodes
        }
        self._execution_order: list[str] = []
        # Pre-compute requires-edge adjacency for fast lookup.
        self._requires_sources: dict[str, list[str]] = {
            nid: [] for nid in graph.nodes
        }
        for edge in graph.edges:
            if edge.edge_type == "requires" and edge.target in self._requires_sources:
                self._requires_sources[edge.target].append(edge.source)

    # -- public queries --------------------------------------------------------

    @property
    def outcomes(self) -> dict[str, NodeOutcome]:
        return dict(self._outcomes)

    def outcome(self, node_id: str) -> NodeOutcome:
        return self._outcomes[node_id]

    def ready_nodes(self) -> list[TaskNodeContract]:
        """Return nodes that are ``PENDING`` and have all requires satisfied.

        Results are sorted by ``node.id`` for determinism.
        """
        ready: list[TaskNodeContract] = []
        for nid in sorted(self._outcomes):
            outcome = self._outcomes[nid]
            if outcome.state != NodeState.PENDING:
                continue
            sources = self._requires_sources.get(nid, [])
            if all(
                self._outcomes[src].state == NodeState.SUCCEEDED for src in sources
            ):
                ready.append(self._graph.nodes[nid])
        return ready

    def is_terminal(self) -> bool:
        """True when no node is ``PENDING`` or ``RUNNING``."""
        return all(
            o.state in (NodeState.SUCCEEDED, NodeState.FAILED, NodeState.BLOCKED)
            for o in self._outcomes.values()
        )

    # -- state transitions -----------------------------------------------------

    def mark_running(self, node_id: str) -> None:
        outcome = self._outcomes[node_id]
        if outcome.state != NodeState.PENDING:
            raise ValueError(
                f"Cannot mark {node_id} as running; current state is {outcome.state.value}."
            )
        outcome.state = NodeState.RUNNING
        self._execution_order.append(node_id)

    def mark_succeeded(self, node_id: str, result: Any = None) -> None:
        outcome = self._outcomes[node_id]
        if outcome.state != NodeState.RUNNING:
            raise ValueError(
                f"Cannot mark {node_id} as succeeded; current state is {outcome.state.value}."
            )
        outcome.state = NodeState.SUCCEEDED
        outcome.result = result

    def mark_failed(self, node_id: str, error: str = "") -> None:
        outcome = self._outcomes[node_id]
        if outcome.state != NodeState.RUNNING:
            raise ValueError(
                f"Cannot mark {node_id} as failed; current state is {outcome.state.value}."
            )
        outcome.state = NodeState.FAILED
        outcome.error = error or None
        # Propagate BLOCKED to all transitive downstream dependents.
        self._propagate_blocked(node_id)

    def mark_blocked(self, node_id: str, error: str = "") -> None:
        """Mark an un-runnable pending node as blocked through the public API."""
        outcome = self._outcomes[node_id]
        if outcome.state != NodeState.PENDING:
            raise ValueError(
                f"Cannot mark {node_id} as blocked; current state is {outcome.state.value}."
            )
        outcome.state = NodeState.BLOCKED
        outcome.error = error or None
        self._propagate_blocked(node_id)

    # -- internal --------------------------------------------------------------

    def _propagate_blocked(self, failed_id: str) -> None:
        """BFS from *failed_id* marking every downstream ``PENDING`` node as ``BLOCKED``."""
        queue = [failed_id]
        visited: set[str] = {failed_id}
        while queue:
            current = queue.pop(0)
            for edge in self._graph.edges:
                if (
                    edge.edge_type == "requires"
                    and edge.source == current
                    and edge.target not in visited
                ):
                    target_outcome = self._outcomes[edge.target]
                    if target_outcome.state == NodeState.PENDING:
                        target_outcome.state = NodeState.BLOCKED
                    visited.add(edge.target)
                    queue.append(edge.target)

    def build_result(self) -> GraphResult:
        return GraphResult(
            node_outcomes=dict(self._outcomes),
            execution_order=list(getattr(self, "_execution_order", [])),
        )
