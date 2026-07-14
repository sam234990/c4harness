"""Tests for phased verification and bounded replanning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from c4harness.core.contracts import (
    FailureCategory,
    FailureRecord,
    VerificationResult,
    WorkerResult,
)
from c4harness.core.graph import TaskNodeContract, VerificationContract
from c4harness.decompose.replan import (
    ReplanAction,
    ReplanReason,
    classify_replan_reason,
    decide_retry,
)
from c4harness.verifier.phases import (
    combine_phase_results,
    verify_integrated_node,
    verify_patch_proposal,
)


class VerificationPhaseTests(unittest.TestCase):
    def test_proposal_checks_do_not_run_post_integration_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            patch = repo / "proposal.patch"
            patch.write_text("--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a\n+b\n")
            contract = VerificationContract(
                deterministic_checks=(
                    "changed_paths_within_allowlist",
                    "patch_non_empty",
                    "command_exit_zero:false",
                )
            )
            result = WorkerResult(
                status="success",
                summary="proposed",
                changed_paths=["a.txt"],
                proposed_patch_path=patch,
            )
            verification = verify_patch_proposal(
                contract,
                result,
                repo,
                write_paths=(str(repo / "a.txt"),),
            )
            self.assertTrue(verification.accepted, verification.issues)

    def test_post_integration_checks_workspace_not_patch_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "created.txt").write_text("done\n")
            contract = VerificationContract(
                deterministic_checks=("patch_non_empty", "file_exists:created.txt")
            )
            result = WorkerResult(status="success", summary="done")
            verification = verify_integrated_node(contract, result, repo)
            self.assertTrue(verification.accepted, verification.issues)

    def test_phase_precedence(self) -> None:
        accepted = VerificationResult(True, "high", memory_facts=["ok"])
        inconclusive = VerificationResult(False, "inconclusive", ["maybe"])
        rejected = VerificationResult(False, "low", ["bad"])
        blocked = VerificationResult(False, "blocked", ["blocked"])
        self.assertEqual(combine_phase_results(accepted, inconclusive).confidence, "inconclusive")
        self.assertEqual(combine_phase_results(inconclusive, rejected).confidence, "low")
        self.assertEqual(combine_phase_results(rejected, blocked).confidence, "blocked")

    def test_policy_violation_blocks_proposal(self) -> None:
        result = WorkerResult(
            status="success",
            summary="bad",
            policy_violations=["write outside consent scope"],
        )
        verification = verify_patch_proposal(VerificationContract(), result, Path.cwd())
        self.assertEqual(verification.confidence, "blocked")


class ReplanDecisionTests(unittest.TestCase):
    def _node(self, attempts: int = 2) -> TaskNodeContract:
        return TaskNodeContract(
            id="n1",
            objective="work",
            max_attempts=attempts,
            verification=VerificationContract(deterministic_checks=("file_exists:x",)),
        )

    def test_missing_file_is_missing_context(self) -> None:
        result = VerificationResult(
            False,
            "low",
            ["[rejected] file_exists: file does not exist: x"],
        )
        self.assertEqual(classify_replan_reason(result), ReplanReason.MISSING_CONTEXT)
        decision = decide_retry(result, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.ADD_CONTEXT)

    def test_verification_failure_retries_within_budget(self) -> None:
        result = VerificationResult(False, "low", ["[rejected] tests_pass: failed"])
        self.assertEqual(decide_retry(result, self._node(), 1).action, ReplanAction.RETRY_SAME_WORKER)
        self.assertEqual(decide_retry(result, self._node(), 2).action, ReplanAction.ESCALATE_MAIN_AGENT)
        self.assertEqual(
            decide_retry(result, self._node(), 1, fallback_available=True).action,
            ReplanAction.SELECT_ANOTHER_WORKER,
        )

    def test_policy_environment_and_conflict_never_retry(self) -> None:
        blocked = VerificationResult(False, "blocked", ["blocked"])
        self.assertEqual(
            decide_retry(blocked, self._node(), 1, policy_blocked=True).action,
            ReplanAction.ESCALATE_MAIN_AGENT,
        )
        self.assertEqual(
            decide_retry(blocked, self._node(), 1, environment_failure=True).action,
            ReplanAction.STOP,
        )
        conflict = decide_retry(blocked, self._node(), 1, integration_conflict=True)
        self.assertEqual(conflict.reason, ReplanReason.CONFLICT_DETECTED)
        self.assertEqual(conflict.action, ReplanAction.ESCALATE_MAIN_AGENT)


# ---------------------------------------------------------------------------
# Phase combination preserves structured failures
# ---------------------------------------------------------------------------


class CombinePhaseFailureTests(unittest.TestCase):
    def test_combine_preserves_failures_from_all_phases(self) -> None:
        f1 = FailureRecord(
            category=FailureCategory.DETERMINISTIC_REJECTION,
            code="failed:file_exists",
            message="missing file",
            phase_or_check="file_exists",
            blame="deterministic_rejection",
        )
        f2 = FailureRecord(
            category=FailureCategory.SEMANTIC_INCONCLUSIVE,
            code="inconclusive:semantic_check",
            message="needs review",
            phase_or_check="semantic_check",
            blame="semantic_inconclusive",
        )
        r1 = VerificationResult(False, "low", ["issue1"], failures=[f1])
        r2 = VerificationResult(False, "inconclusive", ["issue2"], failures=[f2])
        combined = combine_phase_results(r1, r2)
        self.assertEqual(len(combined.failures), 2)
        self.assertEqual(combined.failures[0].category, FailureCategory.DETERMINISTIC_REJECTION)
        self.assertEqual(combined.failures[1].category, FailureCategory.SEMANTIC_INCONCLUSIVE)

    def test_combine_preserves_failures_on_blocked(self) -> None:
        f = FailureRecord(
            category=FailureCategory.POLICY_PERMISSION,
            code="policy:violation",
            message="blocked",
            phase_or_check="policy",
            blame="policy_permission",
        )
        blocked = VerificationResult(False, "blocked", ["blocked"], failures=[f])
        accepted = VerificationResult(True, "high", [], [])
        combined = combine_phase_results(accepted, blocked)
        self.assertEqual(combined.confidence, "blocked")
        self.assertEqual(len(combined.failures), 1)
        self.assertEqual(combined.failures[0].category, FailureCategory.POLICY_PERMISSION)

    def test_combine_empty_with_failures(self) -> None:
        combined = combine_phase_results()
        self.assertEqual(combined.failures, [])


# ---------------------------------------------------------------------------
# Phase verification produces structured failures
# ---------------------------------------------------------------------------


class PhaseVerificationFailureTests(unittest.TestCase):
    def test_worker_failure_produces_retryable_failure(self) -> None:
        result = WorkerResult(status="failed", summary="broken")
        vr = verify_patch_proposal(VerificationContract(), result, Path.cwd())
        self.assertFalse(vr.accepted)
        self.assertTrue(len(vr.failures) > 0)
        f = vr.failures[0]
        self.assertEqual(f.category, FailureCategory.WORKER)
        self.assertTrue(f.retryable)
        self.assertEqual(f.blame, "worker")

    def test_policy_violation_produces_non_retryable_failure(self) -> None:
        result = WorkerResult(
            status="success",
            summary="bad",
            policy_violations=["write outside consent scope"],
        )
        vr = verify_patch_proposal(VerificationContract(), result, Path.cwd())
        self.assertFalse(vr.accepted)
        self.assertTrue(len(vr.failures) > 0)
        f = vr.failures[0]
        self.assertEqual(f.category, FailureCategory.POLICY_PERMISSION)
        self.assertFalse(f.retryable)


# ---------------------------------------------------------------------------
# Replanning with structured failures
# ---------------------------------------------------------------------------


class ReplanStructuredFailureTests(unittest.TestCase):
    def _node(self, attempts: int = 2) -> TaskNodeContract:
        return TaskNodeContract(
            id="n1",
            objective="work",
            max_attempts=attempts,
            verification=VerificationContract(deterministic_checks=("file_exists:x",)),
        )

    def test_policy_failure_never_retries_with_structured_failures(self) -> None:
        f = FailureRecord(
            category=FailureCategory.POLICY_PERMISSION,
            code="policy:violation",
            message="blocked",
            phase_or_check="policy",
            retryable=False,
            blame="policy_permission",
        )
        vr = VerificationResult(False, "blocked", ["blocked"], failures=[f])
        decision = decide_retry(vr, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.ESCALATE_MAIN_AGENT)

    def test_environment_failure_never_retries_with_structured_failures(self) -> None:
        f = FailureRecord(
            category=FailureCategory.ENVIRONMENT,
            code="blocked:command_exit_zero",
            message="timed out",
            phase_or_check="command_exit_zero",
            retryable=False,
            blame="environment",
        )
        vr = VerificationResult(False, "blocked", ["blocked"], failures=[f])
        decision = decide_retry(vr, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.STOP)

    def test_integration_conflict_never_retries_with_structured_failures(self) -> None:
        f = FailureRecord(
            category=FailureCategory.INTEGRATION_CONFLICT,
            code="conflict:merge",
            message="merge conflict",
            phase_or_check="integration",
            retryable=False,
            blame="integration_conflict",
        )
        vr = VerificationResult(False, "blocked", ["blocked"], failures=[f])
        decision = decide_retry(vr, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.ESCALATE_MAIN_AGENT)
        self.assertEqual(decision.reason, ReplanReason.CONFLICT_DETECTED)

    def test_missing_context_structured_failure_prefers_add_context(self) -> None:
        f = FailureRecord(
            category=FailureCategory.MISSING_CONTEXT,
            code="failed:file_exists",
            message="file not found",
            phase_or_check="file_exists",
            retryable=False,
            blame="missing_context",
        )
        vr = VerificationResult(False, "low", ["[rejected] file_exists: missing"], failures=[f])
        decision = decide_retry(vr, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.ADD_CONTEXT)

    def test_retryable_worker_failure_retries(self) -> None:
        f = FailureRecord(
            category=FailureCategory.WORKER,
            code="worker:failed",
            message="worker broke",
            phase_or_check="precheck",
            retryable=True,
            blame="worker",
        )
        vr = VerificationResult(False, "low", ["worker failed"], failures=[f])
        decision = decide_retry(vr, self._node(), 1)
        self.assertEqual(decision.action, ReplanAction.RETRY_SAME_WORKER)

    def test_retryable_worker_failure_uses_fallback_when_available(self) -> None:
        f = FailureRecord(
            category=FailureCategory.WORKER,
            code="worker:failed",
            message="worker broke",
            phase_or_check="precheck",
            retryable=True,
            blame="worker",
        )
        vr = VerificationResult(False, "low", ["worker failed"], failures=[f])
        decision = decide_retry(vr, self._node(), 1, fallback_available=True)
        self.assertEqual(decision.action, ReplanAction.SELECT_ANOTHER_WORKER)

    def test_max_two_attempts_enforced(self) -> None:
        f = FailureRecord(
            category=FailureCategory.WORKER,
            code="worker:failed",
            message="worker broke",
            phase_or_check="precheck",
            retryable=True,
            blame="worker",
        )
        vr = VerificationResult(False, "low", ["worker failed"], failures=[f])
        # Attempt 2/2 — at budget, should escalate.
        decision = decide_retry(vr, self._node(), 2)
        self.assertEqual(decision.action, ReplanAction.ESCALATE_MAIN_AGENT)


# ---------------------------------------------------------------------------
# Deterministic rejection classification
# ---------------------------------------------------------------------------


class DeterministicRejectionClassificationTests(unittest.TestCase):
    def test_classify_from_structured_failures_deterministic_rejection(self) -> None:
        f = FailureRecord(
            category=FailureCategory.DETERMINISTIC_REJECTION,
            code="failed:tests_pass",
            message="tests failed",
            phase_or_check="tests_pass",
            retryable=False,
            blame="deterministic_rejection",
        )
        vr = VerificationResult(False, "low", ["[rejected] tests_pass: failed"], failures=[f])
        reason = classify_replan_reason(vr)
        self.assertEqual(reason, ReplanReason.VERIFICATION_FAILED)

    def test_classify_from_structured_failures_semantic_inconclusive(self) -> None:
        f = FailureRecord(
            category=FailureCategory.SEMANTIC_INCONCLUSIVE,
            code="inconclusive:semantic_check",
            message="needs review",
            phase_or_check="semantic_check",
            retryable=False,
            blame="semantic_inconclusive",
        )
        vr = VerificationResult(False, "inconclusive", ["inconclusive"], failures=[f])
        reason = classify_replan_reason(vr)
        self.assertEqual(reason, ReplanReason.VERIFICATION_INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
