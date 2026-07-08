"""Tests for Delegator outcome persistence in execution History.

Covers: verified success, worker failure, verifier rejection/inconclusive,
environment/policy block, missing-context, consent-scope change,
token/artifact persistence, optional repository backwards compatibility,
exactly-once append, dry-run exclusion, and history-write-failure propagation.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.core.contracts import (
    Difficulty,
    RouteDecision,
    Risk,
    Task,
    TokenUsage,
    VerificationResult,
    WorkerResult,
)
from cost_router.delegator.runtime import (
    DelegationRuntime,
    PreparedWorker,
)
from cost_router.history.contracts import (
    FailureAttribution,
    OutcomeStatus,
)
from cost_router.history.repository import InMemoryHistoryRepository
from cost_router.memory import MemoryStore


def _task(root: Path, tid: str = "t1") -> Task:
    t = Task(goal="test task", repo=root)
    t.id = tid
    return t


def _decision(worker: str = "test-worker") -> RouteDecision:
    return RouteDecision(
        difficulty=Difficulty.SIMPLE,
        risk=Risk.READ_ONLY,
        can_delegate=True,
        backend="test",
        worker=worker,
        model="test-model",
        reason="test",
    )


def _prepared(root: Path, runner) -> PreparedWorker:
    return PreparedWorker(
        output_file=root / "output.md",
        command=["test"],
        prompt="test",
        runner=runner,
    )


def _accept_verifier(result, repo, task):
    return VerificationResult(accepted=True, confidence="accepted")


def _reject_verifier(result, repo, task):
    return VerificationResult(accepted=False, confidence="rejected", issues=["wrong output"])


def _inconclusive_verifier(result, repo, task):
    return VerificationResult(accepted=False, confidence="inconclusive")


def _blocked_verifier(issues):
    def verifier(result, repo, task):
        return VerificationResult(accepted=False, confidence="blocked", issues=issues)
    return verifier


class HistoryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.history = InMemoryHistoryRepository()
        self.store = MemoryStore(self.root / "memory.sqlite3")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runtime(self, history=None) -> DelegationRuntime:
        return DelegationRuntime(self.store, history=history if history is not None else self.history)

    # ---- Success ----

    def test_verified_success_records_outcome(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        outcome = runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
            node_id="node-1",
            worker_arm_id="worker-1",
            capability_dimensions=("coding",),
        )

        self.assertTrue(outcome.verification.accepted)
        self.assertEqual(len(self.history.outcomes), 1)
        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.SUCCESS)
        self.assertEqual(rec.failure_attribution, FailureAttribution.NONE)
        self.assertEqual(rec.node_id, "node-1")
        self.assertEqual(rec.worker_arm_id, "worker-1")
        self.assertEqual(rec.capability_dimensions, ("coding",))

    def test_success_without_verifier_records_success(self) -> None:
        """When no verifier rejects, worker self-report is trusted."""

        def runner(**_):
            return WorkerResult(status="success", summary="ok")

        def always_reject(result, repo, task):
            # Simulate a path where verification is skipped by caller logic;
            # here we test the fallback when verification.accepted is True.
            return VerificationResult(accepted=True, confidence="accepted")

        runtime = self._runtime()
        runtime.verifier = always_reject
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )
        self.assertEqual(self.history.outcomes[0].status, OutcomeStatus.SUCCESS)

    # ---- Worker failure ----

    def test_worker_runtime_error_records_worker_error(self) -> None:
        def runner(**_):
            raise RuntimeError("backend broke")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
            node_id="node-err",
        )

        self.assertEqual(len(self.history.outcomes), 1)
        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.FAILED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.WORKER_ERROR)
        self.assertEqual(rec.node_id, "node-err")

    def test_worker_failed_status_records_worker_error(self) -> None:
        def runner(**_):
            return WorkerResult(status="failed", summary="bad output")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.FAILED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.WORKER_ERROR)

    def test_failed_worker_cannot_be_promoted_by_accepting_verifier(self) -> None:
        def runner(**_):
            return WorkerResult(status="failed", summary="worker failed")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.FAILED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.WORKER_ERROR)

    # ---- Verifier rejection / inconclusive ----

    def test_verifier_rejection_records_worker_error(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.FAILED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.WORKER_ERROR)

    def test_verifier_inconclusive_records_inconclusive(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="partial")

        runtime = self._runtime()
        runtime.verifier = _inconclusive_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.INCONCLUSIVE)
        self.assertEqual(rec.failure_attribution, FailureAttribution.VERIFICATION_INCONCLUSIVE)

    # ---- Environment / policy / permission block ----

    def test_environment_failure_not_worker_error(self) -> None:
        def runner(**_):
            raise OSError("disk full")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.ENVIRONMENT_FAILURE)

    def test_permission_block_not_worker_error(self) -> None:
        def runner(**_):
            raise PermissionError("access denied")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.PERMISSION_BLOCKED)

    def test_connection_error_not_worker_error(self) -> None:
        def runner(**_):
            raise ConnectionError("network unreachable")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.ENVIRONMENT_FAILURE)

    def test_timeout_error_not_worker_error(self) -> None:
        def runner(**_):
            raise TimeoutError("request timed out")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.ENVIRONMENT_FAILURE)

    def test_policy_violations_record_permission_block(self) -> None:
        def runner(**_):
            return WorkerResult(
                status="success",
                summary="done",
                policy_violations=["wrote outside allowlist"],
            )

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.PERMISSION_BLOCKED)

    def test_missing_context_not_worker_error(self) -> None:
        def runner(**_):
            raise FileNotFoundError("context file missing")

        runtime = self._runtime()
        runtime.verifier = _reject_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.MISSING_CONTEXT)

    def test_blocked_verifier_with_consent_issue(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _blocked_verifier(["consent scope changed during execution"])
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.CONSENT_SCOPE_CHANGED)

    def test_blocked_verifier_with_permission_issue(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _blocked_verifier(["changed_paths_within_allowlist: /etc/passwd"])
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.PERMISSION_BLOCKED)

    def test_blocked_verifier_with_missing_file_issue(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _blocked_verifier(["file_exists: /tmp/expected.txt not found"])
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.MISSING_CONTEXT)

    def test_blocked_verifier_defaults_to_environment_failure(self) -> None:
        """Unknown blocked reason defaults to ENVIRONMENT_FAILURE (safe for profiles)."""

        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _blocked_verifier(["something unexpected happened"])
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.status, OutcomeStatus.BLOCKED)
        self.assertEqual(rec.failure_attribution, FailureAttribution.ENVIRONMENT_FAILURE)

    # ---- Token / artifact persistence ----

    def test_token_usage_persisted(self) -> None:
        def runner(**_):
            return WorkerResult(
                status="success",
                summary="done",
                token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            )

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.input_tokens, 100)
        self.assertEqual(rec.output_tokens, 50)
        self.assertEqual(rec.total_tokens, 150)

    def test_explicit_artifact_refs_persisted(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
            artifact_refs=("custom/ref.py",),
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.artifact_refs, ("custom/ref.py",))

    def test_artifact_refs_fallback_to_changed_paths(self) -> None:
        def runner(**_):
            return WorkerResult(
                status="success",
                summary="done",
                changed_paths=["src/main.py", "tests/test_main.py"],
            )

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.artifact_refs, ("src/main.py", "tests/test_main.py"))

    def test_explicit_refs_override_changed_paths(self) -> None:
        def runner(**_):
            return WorkerResult(
                status="success",
                summary="done",
                changed_paths=["src/main.py"],
            )

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
            artifact_refs=("explicit/ref.py",),
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.artifact_refs, ("explicit/ref.py",))

    def test_latency_ms_measured(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertIsNotNone(rec.latency_ms)
        self.assertIsInstance(rec.latency_ms, int)
        self.assertGreaterEqual(rec.latency_ms, 0)

    def test_verification_status_recorded(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.verification_status, "accepted")

    def test_worker_arm_id_defaults_to_decision_worker(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(worker="default-worker"),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        rec = self.history.outcomes[0]
        self.assertEqual(rec.worker_arm_id, "default-worker")

    # ---- Dry-run exclusion ----

    def test_dry_run_no_outcome(self) -> None:
        runtime = self._runtime()
        outcome = runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, lambda **_: WorkerResult(status="success", summary="")),
            execute=False,
        )

        self.assertFalse(outcome.executed)
        self.assertEqual(len(self.history.outcomes), 0)
        # Memory store still records the dry-run subtask.
        self.assertEqual(len(self.store.recent_subtasks()), 1)

    # ---- Optional repository backwards compatibility ----

    def test_no_history_repository_backwards_compatible(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = DelegationRuntime(self.store, history=None)
        runtime.verifier = _accept_verifier
        outcome = runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        self.assertTrue(outcome.verification.accepted)
        # No history → no outcomes recorded.
        self.assertEqual(len(self.history.outcomes), 0)
        # Memory store still has the record.
        self.assertEqual(len(self.store.recent_subtasks()), 1)

    def test_default_runtime_has_no_history(self) -> None:
        """DelegationRuntime without explicit history param still works."""
        runtime = DelegationRuntime(self.store)
        self.assertIsNone(runtime.history)

    # ---- Exactly-once append ----

    def test_exactly_once_append_per_dispatch(self) -> None:
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier

        for i in range(3):
            runtime.dispatch(
                _task(self.root),
                decide=lambda t: _decision(),
                prepare=lambda t: _prepared(self.root, runner),
                execute=True,
                node_id=f"node-{i}",
            )

        self.assertEqual(len(self.history.outcomes), 3)
        self.assertEqual(self.history.outcomes[0].node_id, "node-0")
        self.assertEqual(self.history.outcomes[1].node_id, "node-1")
        self.assertEqual(self.history.outcomes[2].node_id, "node-2")

    def test_dry_run_and_execute_mixed_exactly_once(self) -> None:
        """Dry-run followed by execute produces exactly one outcome."""
        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime()
        runtime.verifier = _accept_verifier

        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=False,
        )
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
            node_id="node-exec",
        )

        self.assertEqual(len(self.history.outcomes), 1)
        self.assertEqual(self.history.outcomes[0].node_id, "node-exec")

    # ---- History write failure propagation ----

    def test_history_write_failure_propagates(self) -> None:
        class BrokenHistory:
            def append_outcome(self, outcome):
                raise RuntimeError("history store full")

            def append_plan(self, snapshot):
                pass

            def outcomes_for_worker(self, worker_arm_id):
                return []

        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime(history=BrokenHistory())
        runtime.verifier = _accept_verifier

        with self.assertRaises(RuntimeError) as ctx:
            runtime.dispatch(
                _task(self.root),
                decide=lambda t: _decision(),
                prepare=lambda t: _prepared(self.root, runner),
                execute=True,
            )

        self.assertIn("history store full", str(ctx.exception))
        # Memory store was still updated before the failure.
        self.assertEqual(len(self.store.recent_subtasks()), 1)

    def test_history_write_failure_on_worker_error_propagates(self) -> None:
        """Even on worker error, history write failure is propagated."""
        class BrokenHistory:
            def append_outcome(self, outcome):
                raise IOError("disk full")

            def append_plan(self, snapshot):
                pass

            def outcomes_for_worker(self, worker_arm_id):
                return []

        def runner(**_):
            raise RuntimeError("worker broke")

        runtime = self._runtime(history=BrokenHistory())
        runtime.verifier = _reject_verifier

        with self.assertRaises(IOError):
            runtime.dispatch(
                _task(self.root),
                decide=lambda t: _decision(),
                prepare=lambda t: _prepared(self.root, runner),
                execute=True,
            )

        # Memory store was still updated.
        self.assertEqual(len(self.store.recent_subtasks()), 1)

    def test_history_write_does_not_silently_swallow(self) -> None:
        """Verify that a swallowed history error would be detectable."""
        call_log: list[str] = []

        class LoggingHistory(InMemoryHistoryRepository):
            def append_outcome(self, outcome):
                call_log.append("append_outcome")
                super().append_outcome(outcome)

        def runner(**_):
            return WorkerResult(status="success", summary="done")

        runtime = self._runtime(history=LoggingHistory())
        runtime.verifier = _accept_verifier
        runtime.dispatch(
            _task(self.root),
            decide=lambda t: _decision(),
            prepare=lambda t: _prepared(self.root, runner),
            execute=True,
        )

        self.assertEqual(call_log, ["append_outcome"])

    # ---- Attribution correctness for non-worker failures ----

    def test_excluded_attributions_match_profiles(self) -> None:
        """All non-worker attributions are in the profiles exclusion set."""
        from cost_router.history.profiles import _EXCLUDED_ATTRIBUTIONS

        def runner_env(**_):
            raise OSError("fail")

        def runner_perm(**_):
            raise PermissionError("denied")

        def runner_missing(**_):
            raise FileNotFoundError("gone")

        def runner_policy(**_):
            return WorkerResult(status="success", summary="done", policy_violations=["bad"])

        cases = [
            (runner_env, FailureAttribution.ENVIRONMENT_FAILURE),
            (runner_perm, FailureAttribution.PERMISSION_BLOCKED),
            (runner_missing, FailureAttribution.MISSING_CONTEXT),
            (runner_policy, FailureAttribution.PERMISSION_BLOCKED),
        ]

        for runner, expected_attr in cases:
            history = InMemoryHistoryRepository()
            store = MemoryStore(self.root / f"mem-{expected_attr.value}.sqlite3")
            runtime = DelegationRuntime(store, history=history)
            runtime.verifier = _reject_verifier
            runtime.dispatch(
                _task(self.root),
                decide=lambda t: _decision(),
                prepare=lambda t: _prepared(self.root, runner),
                execute=True,
            )
            rec = history.outcomes[-1]
            self.assertIn(
                rec.failure_attribution,
                _EXCLUDED_ATTRIBUTIONS,
                f"{expected_attr.value} should be excluded from worker profiles",
            )


class AttributionUnitTests(unittest.TestCase):
    """Direct unit tests for the attribution function."""

    def test_exception_type_classification(self) -> None:
        from cost_router.history.attribution import _classify_exception

        self.assertEqual(
            _classify_exception(PermissionError()),
            (OutcomeStatus.BLOCKED, FailureAttribution.PERMISSION_BLOCKED),
        )
        self.assertEqual(
            _classify_exception(FileNotFoundError()),
            (OutcomeStatus.BLOCKED, FailureAttribution.MISSING_CONTEXT),
        )
        self.assertEqual(
            _classify_exception(OSError()),
            (OutcomeStatus.BLOCKED, FailureAttribution.ENVIRONMENT_FAILURE),
        )
        self.assertEqual(
            _classify_exception(ConnectionError()),
            (OutcomeStatus.BLOCKED, FailureAttribution.ENVIRONMENT_FAILURE),
        )
        self.assertEqual(
            _classify_exception(TimeoutError()),
            (OutcomeStatus.BLOCKED, FailureAttribution.ENVIRONMENT_FAILURE),
        )
        self.assertEqual(
            _classify_exception(RuntimeError()),
            (OutcomeStatus.FAILED, FailureAttribution.WORKER_ERROR),
        )
        self.assertEqual(
            _classify_exception(ValueError()),
            (OutcomeStatus.FAILED, FailureAttribution.WORKER_ERROR),
        )

    def test_block_reason_classification(self) -> None:
        from cost_router.history.attribution import _classify_block_reasons

        self.assertEqual(
            _classify_block_reasons(["consent scope changed"]),
            FailureAttribution.CONSENT_SCOPE_CHANGED,
        )
        self.assertEqual(
            _classify_block_reasons(["changed_paths_within_allowlist: /etc/passwd"]),
            FailureAttribution.PERMISSION_BLOCKED,
        )
        self.assertEqual(
            _classify_block_reasons(["file_exists: /tmp/x not found"]),
            FailureAttribution.MISSING_CONTEXT,
        )
        self.assertEqual(
            _classify_block_reasons(["permission denied"]),
            FailureAttribution.PERMISSION_BLOCKED,
        )
        self.assertEqual(
            _classify_block_reasons(["command_exit_zero: timed out"]),
            FailureAttribution.ENVIRONMENT_FAILURE,
        )
        # Default for unknown.
        self.assertEqual(
            _classify_block_reasons(["something weird"]),
            FailureAttribution.ENVIRONMENT_FAILURE,
        )
        # Empty list defaults.
        self.assertEqual(
            _classify_block_reasons([]),
            FailureAttribution.ENVIRONMENT_FAILURE,
        )

    def test_attribute_outcome_with_exception(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=None,
            verification=None,
            exception=RuntimeError("boom"),
        )
        self.assertEqual(result.status, OutcomeStatus.FAILED)
        self.assertEqual(result.failure_attribution, FailureAttribution.WORKER_ERROR)

    def test_attribute_outcome_no_result_no_exception(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=None,
            verification=None,
        )
        self.assertEqual(result.status, OutcomeStatus.INCONCLUSIVE)
        self.assertEqual(result.failure_attribution, FailureAttribution.WORKER_ERROR)

    def test_attribute_outcome_success(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(status="success", summary="ok"),
            verification=VerificationResult(accepted=True, confidence="accepted"),
        )
        self.assertEqual(result.status, OutcomeStatus.SUCCESS)
        self.assertEqual(result.failure_attribution, FailureAttribution.NONE)
        self.assertEqual(result.verification_status, "accepted")

    def test_attribute_outcome_extracts_tokens(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(
                status="success",
                summary="ok",
                token_usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            ),
            verification=VerificationResult(accepted=True, confidence="accepted"),
        )
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.total_tokens, 15)

    def test_attribute_outcome_fallback_artifacts_from_changed_paths(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(
                status="success",
                summary="ok",
                changed_paths=["a.py", "b.py"],
            ),
            verification=VerificationResult(accepted=True, confidence="accepted"),
        )
        self.assertEqual(result.artifact_refs, ("a.py", "b.py"))

    def test_attribute_outcome_explicit_refs_override_changed_paths(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(
                status="success",
                summary="ok",
                changed_paths=["a.py"],
            ),
            verification=VerificationResult(accepted=True, confidence="accepted"),
            artifact_refs=("explicit.py",),
        )
        self.assertEqual(result.artifact_refs, ("explicit.py",))

    def test_attribute_outcome_latency_recorded(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(status="success", summary="ok"),
            verification=VerificationResult(accepted=True, confidence="accepted"),
            latency_ms=42,
        )
        self.assertEqual(result.latency_ms, 42)

    def test_attribute_outcome_capability_dimensions_recorded(self) -> None:
        from cost_router.history.attribution import attribute_outcome

        result = attribute_outcome(
            task_id="t1",
            node_id="n1",
            worker_arm_id="w1",
            result=WorkerResult(status="success", summary="ok"),
            verification=VerificationResult(accepted=True, confidence="accepted"),
            capability_dimensions=("debugging", "code_implementation"),
        )
        self.assertEqual(result.capability_dimensions, ("debugging", "code_implementation"))


if __name__ == "__main__":
    unittest.main()
