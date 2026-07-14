"""Application service for task-contract graph execution.

``RunGraph`` is the application-level orchestrator that:

1. Builds a :class:`GraphScheduler` from a :class:`TaskContractGraph`.
2. Iterates ready nodes respecting dependency order and write-path
   overlap constraints.
3. Calls an injected ``NodeRunner`` for each ready node.
4. Reports outcomes back to the scheduler so blocking propagation works.
5. Returns an inspectable :class:`GraphResult`.

When ``max_parallel > 1``, ready nodes whose declared write paths do
not overlap (by equality or ancestor/descendant) may execute
concurrently using a thread pool.  Nodes with overlapping writes are
serialized with deterministic lexicographic selection.

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

import concurrent.futures
from dataclasses import dataclass, field, replace
from pathlib import Path
import threading
from typing import Any, Callable
from uuid import uuid4

from ..core.contracts import (
    Evidence,
    FailureCategory,
    FailureRecord,
    RouteDecision,
    Task,
    TaskConstraints,
    TaskMode,
    VerificationResult,
)
from ..core.graph import (
    DecompositionPlan,
    ExecutionMode,
    TaskContractGraph,
    TaskNodeContract,
    VerificationContract,
)
from ..delegator.runtime import DelegationOutcome, DelegationRuntime, PreparedWorker
from ..delegator.scheduler import (
    GraphResult,
    GraphScheduler,
    NodeState,
    select_parallel_batch,
)
from ..decompose.replan import ReplanAction, ReplanDecision, decide_retry
from ..integrator import GraphIntegrationSession, IntegrationAttempt
from ..verifier.phases import (
    combine_phase_results,
    verify_integrated_node,
    verify_patch_proposal,
)
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
    """Task-contract graph executor with optional bounded parallelism.

    Parameters
    ----------
    graph:
        The compiled task-contract graph (must be acyclic).
    runner:
        A callable that executes a single node and returns a
        :class:`NodeResult`.  Backend selection is the caller's
        responsibility.
    max_parallel:
        Maximum number of nodes that may execute concurrently.
        Defaults to ``1`` (sequential).  Values greater than ``1``
        enable dependency-aware bounded concurrency where ready nodes
        with non-overlapping write sets run in parallel.
    """

    def __init__(
        self,
        graph: TaskContractGraph,
        runner: NodeRunner | None = None,
        max_parallel: int = 1,
        repo: Path | None = None,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be at least 1")
        self._graph = graph
        self._runner = runner or _noop_runner
        self._max_parallel = max_parallel
        self._repo = repo

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

            if self._max_parallel <= 1:
                # --- Sequential: one node at a time (original behaviour) ---
                node = ready[0]
                scheduler.mark_running(node.id)

                if not execute:
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
            else:
                # --- Bounded parallel batch ---
                batch = select_parallel_batch(
                    ready,
                    self._max_parallel,
                    repo=self._repo,
                )

                # Mark all batch members as RUNNING before any execution.
                for node in batch:
                    scheduler.mark_running(node.id)

                if not execute:
                    for node in batch:
                        scheduler.mark_succeeded(node.id, result=None)
                    continue

                if len(batch) == 1:
                    # Single node — avoid thread-pool overhead.
                    node = batch[0]
                    try:
                        node_result = self._runner(node)
                    except Exception as exc:
                        scheduler.mark_failed(
                            node.id, error=f"{type(exc).__name__}: {exc}"
                        )
                        continue
                    if node_result.success:
                        scheduler.mark_succeeded(node.id, result=node_result.result)
                    else:
                        scheduler.mark_failed(node.id, error=node_result.error)
                else:
                    # True concurrent execution.
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=len(batch)
                    ) as pool:
                        futures = {
                            pool.submit(self._runner, node): node
                            for node in batch
                        }
                        for future in concurrent.futures.as_completed(futures):
                            node = futures[future]
                            try:
                                node_result = future.result()
                            except Exception as exc:
                                scheduler.mark_failed(
                                    node.id,
                                    error=f"{type(exc).__name__}: {exc}",
                                )
                                continue
                            if node_result.success:
                                scheduler.mark_succeeded(
                                    node.id, result=node_result.result
                                )
                            else:
                                scheduler.mark_failed(
                                    node.id, error=node_result.error
                                )

        return scheduler.build_result()


NodeDecisionFactory = Callable[[TaskNodeContract, Task], RouteDecision]
NodePreparationFactory = Callable[[TaskNodeContract, Task], PreparedWorker]
FallbackWorkerFactory = Callable[[TaskNodeContract, int], str | None]


@dataclass(slots=True)
class GraphExecutionReport:
    """End-to-end result for one contract-graph execution."""

    graph_result: GraphResult
    node_verifications: dict[str, VerificationResult] = field(default_factory=dict)
    node_evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    root_verification: RootVerificationResult | None = None
    integration_workspace: Path | None = None
    node_attempts: dict[str, int] = field(default_factory=dict)
    replan_decisions: dict[str, list[ReplanDecision]] = field(default_factory=dict)

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
            "integration_workspace": (
                str(self.integration_workspace) if self.integration_workspace else None
            ),
            "node_attempts": dict(self.node_attempts),
            "replan_decisions": {
                node_id: [
                    {
                        "action": decision.action.value,
                        "reason": decision.reason.value,
                        "explanation": decision.explanation,
                    }
                    for decision in decisions
                ]
                for node_id, decisions in self.replan_decisions.items()
            },
        }


class GraphExecutionService:
    """Compose graph scheduling, delegation, node verification, and root verification."""

    def __init__(
        self,
        runtime: DelegationRuntime,
        *,
        decide: NodeDecisionFactory,
        prepare: NodePreparationFactory,
        fallback_worker: FallbackWorkerFactory | None = None,
        integration_parent_dir: Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.decide = decide
        self.prepare = prepare
        self.fallback_worker = fallback_worker
        self.integration_parent_dir = integration_parent_dir

    def execute(
        self,
        plan: DecompositionPlan,
        base_task: Task,
        *,
        execute: bool = True,
        max_parallel: int = 1,
        explicit_root_decisions: dict[str, bool] | None = None,
    ) -> GraphExecutionReport:
        node_verifications: dict[str, VerificationResult] = {}
        node_evidence: dict[str, list[Evidence]] = {}
        node_attempts: dict[str, int] = {}
        replan_decisions: dict[str, list[ReplanDecision]] = {}
        state_lock = threading.RLock()
        integration: GraphIntegrationSession | None = None
        if execute:
            parent = self.integration_parent_dir or (
                plan.situation.repo / ".c4harness" / "graph-runs"
            )
            integration = GraphIntegrationSession.create(
                plan.situation.repo,
                graph_id=f"{plan.situation.task_id}-{uuid4().hex[:8]}",
                parent_dir=parent,
            )

        def run_node(node: TaskNodeContract) -> NodeResult:
            assert integration is not None
            execution_node = self._node_for_workspace(
                node,
                plan.situation.repo,
                integration,
            )
            active_node = execution_node
            last_outcome: DelegationOutcome | None = None
            retry_feedback = ""
            try:
                if execution_node.write_paths:
                    integration.reserve(node.id, node.write_paths)
                for attempt in range(1, node.max_attempts + 1):
                    with state_lock:
                        node_attempts[node.id] = attempt
                    task = self._task_for_node(
                        plan,
                        base_task,
                        active_node,
                        execution_repo=integration.root,
                    )
                    if retry_feedback:
                        task.goal += (
                            "\n\nPrevious attempt failed verification. Correct these issues:\n- "
                            + "\n- ".join(retry_feedback.splitlines())
                        )
                    integration_holder: dict[str, IntegrationAttempt] = {}

                    def phased_verifier(result, repo, _task):
                        if active_node.execution_mode != ExecutionMode.PATCH:
                            return verify_integrated_node(
                                active_node.verification,
                                result,
                                repo,
                                write_paths=tuple(str(path) for path in active_node.write_paths),
                                requirement_refs=active_node.requirement_refs,
                                required_requirement_ids=active_node.requirement_refs,
                            )
                        proposal = verify_patch_proposal(
                            active_node.verification,
                            result,
                            repo,
                            write_paths=tuple(str(path) for path in active_node.write_paths),
                            requirement_refs=active_node.requirement_refs,
                            required_requirement_ids=active_node.requirement_refs,
                        )
                        if not proposal.accepted:
                            return proposal
                        if result.proposed_patch_path is None:
                            return VerificationResult(
                                False,
                                "low",
                                ["[rejected] patch_non_empty: no proposed patch path"],
                                failures=[FailureRecord(
                                    category=FailureCategory.CONTRACT,
                                    code="patch_missing",
                                    message="Worker did not return a proposed patch path.",
                                    phase_or_check="proposal",
                                    retryable=True,
                                    blame="worker",
                                )],
                            )
                        integration_attempt = integration.apply_proposal(
                            patch_path=result.proposed_patch_path,
                            write_paths=node.write_paths,
                        )
                        integration_holder["attempt"] = integration_attempt
                        if integration_attempt.conflicts:
                            return VerificationResult(
                                False,
                                "blocked",
                                [
                                    "[integration_conflict] "
                                    + "; ".join(conflict.detail or conflict.path for conflict in integration_attempt.conflicts)
                                ],
                                failures=[FailureRecord(
                                    category=FailureCategory.INTEGRATION_CONFLICT,
                                    code="integration_conflict",
                                    message="; ".join(
                                        conflict.detail or conflict.path
                                        for conflict in integration_attempt.conflicts
                                    ),
                                    phase_or_check="integration",
                                    retryable=False,
                                    blame="integration_conflict",
                                )],
                            )
                        if not integration_attempt.accepted:
                            return VerificationResult(
                                False,
                                "low",
                                [f"[rejected] patch_integration: {issue}" for issue in integration_attempt.issues],
                                failures=[
                                    FailureRecord(
                                        category=FailureCategory.DETERMINISTIC_REJECTION,
                                        code="patch_integration",
                                        message=issue,
                                        phase_or_check="integration",
                                        retryable=True,
                                        blame="worker",
                                    )
                                    for issue in integration_attempt.issues
                                ],
                            )
                        actual_paths = {
                            change.path
                            for change in (
                                integration_attempt.patch_result.applied
                                if integration_attempt.patch_result is not None
                                else ()
                            )
                        }
                        reported_paths = {
                            integration.relative_path(Path(path))
                            for path in result.changed_paths
                        }
                        if actual_paths != reported_paths:
                            integration.rollback(integration_attempt)
                            return VerificationResult(
                                False,
                                "low",
                                [
                                    "[rejected] changed_paths_match_patch: "
                                    f"reported={sorted(reported_paths)}, actual={sorted(actual_paths)}"
                                ],
                                failures=[FailureRecord(
                                    category=FailureCategory.POLICY_PERMISSION,
                                    code="changed_paths_mismatch",
                                    message=(
                                        f"reported={sorted(reported_paths)}, "
                                        f"actual={sorted(actual_paths)}"
                                    ),
                                    phase_or_check="proposal",
                                    retryable=False,
                                    blame="worker",
                                )],
                            )
                        post = verify_integrated_node(
                            active_node.verification,
                            result,
                            repo,
                            write_paths=tuple(str(path) for path in active_node.write_paths),
                            requirement_refs=active_node.requirement_refs,
                            required_requirement_ids=active_node.requirement_refs,
                        )
                        side_effects = integration.post_verification_issues(
                            integration_attempt
                        )
                        if side_effects:
                            integration.rollback(integration_attempt)
                            return VerificationResult(
                                False,
                                "blocked",
                                [
                                    f"[blocked] post_verifier_side_effect: {issue}"
                                    for issue in side_effects
                                ],
                                failures=[
                                    FailureRecord(
                                        category=FailureCategory.POLICY_PERMISSION,
                                        code="post_verifier_side_effect",
                                        message=issue,
                                        phase_or_check="post_integration",
                                        retryable=False,
                                        blame="policy_permission",
                                    )
                                    for issue in side_effects
                                ],
                            )
                        combined = combine_phase_results(proposal, post)
                        if not combined.accepted:
                            integration.rollback(integration_attempt)
                        return combined

                    try:
                        outcome = self.runtime.dispatch(
                            task,
                            decide=lambda current: self.decide(active_node, current),
                            prepare=lambda current: self.prepare(active_node, current),
                            execute=True,
                            node_id=node.id,
                            worker_arm_id=active_node.assigned_worker_id,
                            capability_dimensions=tuple(sorted(node.soft_capabilities)),
                            verifier=phased_verifier,
                        )
                    except Exception:
                        pending = integration_holder.get("attempt")
                        if pending is not None and pending.patch_result is not None:
                            integration.rollback(pending)
                        raise
                    last_outcome = outcome
                    verification = outcome.verification or VerificationResult(
                        False, "low", ["Missing verification result."]
                    )
                    result = outcome.result
                    with state_lock:
                        node_verifications[node.id] = verification
                        if result is not None:
                            node_evidence[node.id] = list(result.evidence)
                    if result is not None and result.status == "success" and verification.accepted:
                        pending = integration_holder.get("attempt")
                        if pending is not None:
                            integration.commit(pending)
                        return self._node_result(outcome, verification, attempt)

                    pending = integration_holder.get("attempt")
                    if (
                        pending is not None
                        and pending.patch_result is not None
                        and pending.patch_result.rollback_dir is not None
                    ):
                        integration.rollback(pending)

                    fallback_id = (
                        self.fallback_worker(active_node, attempt)
                        if self.fallback_worker is not None and attempt < node.max_attempts
                        else None
                    )
                    integration_attempt = integration_holder.get("attempt")
                    decision = decide_retry(
                        verification,
                        active_node,
                        attempt,
                        integration_conflict=bool(
                            integration_attempt and integration_attempt.conflicts
                        ),
                        policy_blocked=bool(result and result.policy_violations),
                        environment_failure=isinstance(
                            outcome.exception,
                            (OSError, ConnectionError, TimeoutError),
                        ),
                        fallback_available=bool(
                            fallback_id and fallback_id != active_node.assigned_worker_id
                        ),
                    )
                    if decision is None:
                        break
                    if decision.action in {
                        ReplanAction.ADD_CONTEXT,
                        ReplanAction.REVISE_CONTRACT,
                    }:
                        decision = ReplanDecision(
                            action=ReplanAction.ESCALATE_MAIN_AGENT,
                            reason=decision.reason,
                            explanation=(
                                f"{decision.action.value} requires a graph mutation "
                                "callback that is not available in v1; escalating to "
                                "the main agent instead of claiming it was executed."
                            ),
                        )
                    with state_lock:
                        replan_decisions.setdefault(node.id, []).append(decision)
                    if decision.action == ReplanAction.RETRY_SAME_WORKER:
                        retry_feedback = "\n".join(verification.issues)
                        continue
                    if decision.action == ReplanAction.SELECT_ANOTHER_WORKER and fallback_id:
                        active_node = replace(active_node, assigned_worker_id=fallback_id)
                        retry_feedback = "\n".join(verification.issues)
                        continue
                    break
            finally:
                integration.release(node.id)

            if last_outcome is None:
                return NodeResult(False, "Node was not dispatched.")
            verification = last_outcome.verification or VerificationResult(
                False, "low", ["Missing verification result."]
            )
            return self._node_result(
                last_outcome,
                verification,
                node_attempts.get(node.id, 0),
            )

        graph_result = RunGraph(
            plan.graph,
            runner=run_node,
            max_parallel=max_parallel,
            repo=plan.situation.repo,
        ).execute(execute=execute)
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
            integration_workspace=integration.root if integration else None,
            node_attempts=node_attempts,
            replan_decisions=replan_decisions,
        )

    @staticmethod
    def _task_for_node(
        plan: DecompositionPlan,
        base_task: Task,
        node: TaskNodeContract,
        *,
        execution_repo: Path | None = None,
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
            repo=execution_repo or plan.situation.repo,
            paths=list(node.allowed_paths),
            write_paths=list(node.write_paths),
            context_packs=list(node.context_packs),
            constraints=constraints,
            parent_task_label=base_task.parent_task_label,
            source_thread_id=base_task.source_thread_id,
            source_harness=base_task.source_harness,
        )

    @staticmethod
    def _node_for_workspace(
        node: TaskNodeContract,
        source_repo: Path,
        integration: GraphIntegrationSession,
    ) -> TaskNodeContract:
        def translate(path: Path) -> Path:
            candidate = path if path.is_absolute() else source_repo / path
            try:
                relative = candidate.resolve().relative_to(source_repo.resolve())
            except ValueError:
                return path
            return integration.root / relative

        def translate_check(expression: str) -> str:
            name, separator, argument = expression.partition(":")
            if not separator:
                return expression
            if name in {"file_exists", "file_contains", "json_schema_valid"}:
                candidate = Path(argument)
                if candidate.is_absolute():
                    return f"{name}:{translate(candidate)}"
            if name in {"command_exit_zero", "tests_pass"}:
                return expression.replace(
                    str(source_repo.resolve()),
                    str(integration.root.resolve()),
                )
            return expression

        def translate_requirement(expression: str) -> str:
            stripped = expression.strip()
            if stripped.startswith("test_command:"):
                command = stripped.partition(":")[2].strip().replace(
                    str(source_repo.resolve()),
                    str(integration.root.resolve()),
                )
                return f"test_command:{command}"
            candidate = Path(stripped)
            if candidate.is_absolute():
                translated = translate(candidate)
                if translated != candidate:
                    return str(translated)
            return expression

        verification = VerificationContract(
            deterministic_checks=tuple(
                translate_check(expression)
                for expression in node.verification.deterministic_checks
            ),
            evidence_requirements=tuple(
                translate_requirement(expression)
                for expression in node.verification.evidence_requirements
            ),
            semantic_check=node.verification.semantic_check,
            root_contribution=node.verification.root_contribution,
        )

        return replace(
            node,
            allowed_paths=tuple(translate(path) for path in node.allowed_paths),
            write_paths=tuple(translate(path) for path in node.write_paths),
            context_packs=tuple(translate(path) for path in node.context_packs),
            verification=verification,
        )

    @staticmethod
    def _node_result(
        outcome: DelegationOutcome,
        verification: VerificationResult,
        attempt: int,
    ) -> NodeResult:
        result = outcome.result
        success = bool(
            result
            and result.status == "success"
            and verification.accepted
        )
        issues = verification.issues or (
            [result.summary] if result and result.status != "success" else []
        )
        return NodeResult(
            success=success,
            error="; ".join(issues),
            result={
                "attempt": attempt,
                "task": outcome.task.to_dict(),
                "decision": outcome.decision.to_dict(),
                "worker_result": result.to_dict() if result else None,
                "verification": verification.to_dict(),
            },
            verification=verification,
            evidence=tuple(result.evidence) if result else (),
        )
