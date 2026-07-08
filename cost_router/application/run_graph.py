"""Application service for sequential task-contract graph execution.

``RunGraph`` is the Phase-2 minimal orchestrator that:

1. Builds a :class:`GraphScheduler` from a :class:`TaskContractGraph`.
2. Iterates ready nodes one at a time (deterministic sequential order).
3. Calls an injected ``NodeRunner`` for each ready node.
4. Reports outcomes back to the scheduler so blocking propagation works.
5. Returns an inspectable :class:`GraphResult`.

Backend selection stays **outside** this module — the caller provides a
``NodeRunner`` (a plain callable) that already knows how to dispatch to
the correct worker.

Design decisions
================
* **NodeRunner protocol** – ``Callable[[TaskNodeContract], NodeResult]``
  where ``NodeResult`` carries ``success: bool`` and optional ``error``
  and ``result`` fields.  Keeping the runner as a simple callable avoids
  coupling to any specific delegator or backend.
* **execute=False / dry-run** – when ``execute=False``, the runner is
  *not* called.  Nodes still transition through ``PENDING → RUNNING →
  SUCCEEDED`` so the caller can inspect the planned execution order.
  This is useful for plan-mode and testing.
* **Failure semantics** – a failed node triggers ``mark_failed`` on the
  scheduler which propagates ``BLOCKED`` to all transitive downstream
  dependents.  The loop continues to drain remaining independent ready
  nodes (they may still succeed even though part of the graph failed).
* **Determinism** – ready nodes are sorted by ``node.id``; the
  scheduler's ``mark_running`` records the actual execution order in
  ``GraphResult.execution_order``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.contracts import Evidence, RouteDecision, Task, TaskConstraints, TaskMode, VerificationResult
from ..core.graph import DecompositionPlan, ExecutionMode, TaskContractGraph, TaskNodeContract
from ..delegator.runtime import DelegationOutcome, DelegationRuntime, PreparedWorker
from ..delegator.scheduler import GraphResult, GraphScheduler, NodeState
from ..verifier.service import verify_node
from .verify_root import verify_root
from ..verifier.root import RootVerificationResult


# ---------------------------------------------------------------------------
# Node runner contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NodeResult:
    """Minimal outcome returned by a node runner."""

    success: bool
    error: str = ""
    result: Any = None
    verification: VerificationResult | None = None
    evidence: tuple[Evidence, ...] = ()


# Type alias for the injected runner.
NodeRunner = Callable[[TaskNodeContract], NodeResult]


# ---------------------------------------------------------------------------
# Default no-op runner (used for dry-run / testing)
# ---------------------------------------------------------------------------

def _noop_runner(_node: TaskNodeContract) -> NodeResult:
    return NodeResult(success=True, result="dry-run")


# ---------------------------------------------------------------------------
# RunGraph
# ---------------------------------------------------------------------------

class RunGraph:
    """Sequential task-contract graph executor.

    Parameters
    ----------
    graph:
        The compiled task-contract graph (must be acyclic).
    runner:
        A callable that executes a single node and returns a
        :class:`NodeResult`.  Backend selection is the caller's
        responsibility.
    """

    def __init__(
        self,
        graph: TaskContractGraph,
        runner: NodeRunner | None = None,
    ) -> None:
        self._graph = graph
        self._runner = runner or _noop_runner

    def execute(self, *, execute: bool = True) -> GraphResult:
        """Run the graph to completion.

        Parameters
        ----------
        execute:
            When ``True``, the runner is called for each ready node.
            When ``False`` (dry-run), nodes are walked in dependency
            order but the runner is skipped — every node is marked
            ``SUCCEEDED`` with ``result=None``.

        Returns
        -------
        GraphResult
            An inspectable result containing per-node outcomes and the
            deterministic execution order.
        """
        scheduler = GraphScheduler(self._graph)

        while not scheduler.is_terminal():
            ready = scheduler.ready_nodes()
            if not ready:
                # No ready nodes and not terminal → deadlock / incomplete.
                # Mark remaining PENDING nodes as BLOCKED so the result
                # reflects the stuck state.
                for nid, outcome in scheduler.outcomes.items():
                    if outcome.state == NodeState.PENDING:
                        scheduler.mark_blocked(
                            nid,
                            "No ready node remained before graph completion.",
                        )
                break

            # Process one node at a time (sequential).
            node = ready[0]
            scheduler.mark_running(node.id)

            if not execute:
                # Dry-run: skip runner, mark succeeded.
                scheduler.mark_succeeded(node.id, result=None)
                continue

            try:
                node_result = self._runner(node)
            except Exception as exc:
                scheduler.mark_failed(node.id, error=f"{type(exc).__name__}: {exc}")
                continue

            if node_result.success:
                scheduler.mark_succeeded(node.id, result=node_result.result)
            else:
                scheduler.mark_failed(node.id, error=node_result.error)

        return scheduler.build_result()


NodeDecisionFactory = Callable[[TaskNodeContract, Task], RouteDecision]
NodePreparationFactory = Callable[[TaskNodeContract, Task], PreparedWorker]


@dataclass(slots=True)
class GraphExecutionReport:
    """End-to-end result for one sequential contract-graph execution."""

    graph_result: GraphResult
    node_verifications: dict[str, VerificationResult] = field(default_factory=dict)
    node_evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    root_verification: RootVerificationResult | None = None

    @property
    def accepted(self) -> bool:
        return bool(self.root_verification and self.root_verification.accepted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_result": self.graph_result.to_dict(),
            "node_verifications": {
                node_id: verification.to_dict()
                for node_id, verification in self.node_verifications.items()
            },
            "node_evidence": {
                node_id: [item.to_dict() for item in evidence]
                for node_id, evidence in self.node_evidence.items()
            },
            "root_verification": (
                self.root_verification.to_dict() if self.root_verification else None
            ),
            "accepted": self.accepted,
        }


class GraphExecutionService:
    """Compose graph scheduling, delegation, node verification, and root verification."""

    def __init__(
        self,
        runtime: DelegationRuntime,
        *,
        decide: NodeDecisionFactory,
        prepare: NodePreparationFactory,
    ) -> None:
        self.runtime = runtime
        self.decide = decide
        self.prepare = prepare

    def execute(
        self,
        plan: DecompositionPlan,
        base_task: Task,
        *,
        execute: bool = True,
        explicit_root_decisions: dict[str, bool] | None = None,
    ) -> GraphExecutionReport:
        node_verifications: dict[str, VerificationResult] = {}
        node_evidence: dict[str, list[Evidence]] = {}

        def run_node(node: TaskNodeContract) -> NodeResult:
            task = self._task_for_node(plan, base_task, node)
            outcome = self.runtime.dispatch(
                task,
                decide=lambda current: self.decide(node, current),
                prepare=lambda current: self.prepare(node, current),
                execute=True,
                node_id=node.id,
                worker_arm_id=node.assigned_worker_id,
                capability_dimensions=tuple(sorted(node.soft_capabilities)),
                verifier=lambda result, repo, _task: verify_node(
                    node,
                    result,
                    repo,
                    required_requirement_ids=node.requirement_refs,
                ),
            )
            verification = outcome.verification
            result = outcome.result
            if verification is not None:
                node_verifications[node.id] = verification
            if result is not None:
                node_evidence[node.id] = list(result.evidence)
            success = bool(
                result
                and result.status == "success"
                and verification
                and verification.accepted
            )
            issues = verification.issues if verification else ["Missing verification result."]
            if result is not None and result.status != "success" and not issues:
                issues = [result.summary or f"Worker status: {result.status}"]
            return NodeResult(
                success=success,
                error="; ".join(issues),
                result={
                    "task": outcome.task.to_dict(),
                    "decision": outcome.decision.to_dict(),
                    "worker_result": result.to_dict() if result else None,
                    "verification": verification.to_dict() if verification else None,
                },
                verification=verification,
                evidence=tuple(result.evidence) if result else (),
            )

        graph_result = RunGraph(plan.graph, runner=run_node).execute(execute=execute)
        if not execute:
            return GraphExecutionReport(graph_result=graph_result)
        root_result = verify_root(
            plan,
            graph_result,
            node_verifications,
            node_evidence=node_evidence,
            explicit_decisions=explicit_root_decisions,
            hooks=self.runtime.hooks,
        )
        return GraphExecutionReport(
            graph_result=graph_result,
            node_verifications=node_verifications,
            node_evidence=node_evidence,
            root_verification=root_result,
        )

    @staticmethod
    def _task_for_node(
        plan: DecompositionPlan,
        base_task: Task,
        node: TaskNodeContract,
    ) -> Task:
        mode = TaskMode.PATCH if node.execution_mode == ExecutionMode.PATCH else TaskMode.READ_ONLY
        constraints = TaskConstraints(
            mode=mode,
            max_runtime_sec=base_task.constraints.max_runtime_sec,
            allow_network=base_task.constraints.allow_network,
            max_output_chars=base_task.constraints.max_output_chars,
            external_policy=base_task.constraints.external_policy,
            data_classification=base_task.constraints.data_classification,
        )
        return Task(
            id=plan.situation.task_id,
            goal=node.objective,
            repo=plan.situation.repo,
            paths=list(node.allowed_paths),
            write_paths=list(node.write_paths),
            context_packs=list(node.context_packs),
            constraints=constraints,
            parent_task_label=base_task.parent_task_label,
            source_thread_id=base_task.source_thread_id,
            source_harness=base_task.source_harness,
        )
