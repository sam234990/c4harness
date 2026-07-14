"""Regression tests for bounded parallel graph integration safety."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from c4harness.application.run_graph import GraphExecutionService
from c4harness.core.contracts import Evidence, WorkerResult
from c4harness.core.graph import TaskNodeContract, VerificationContract
from c4harness.delegator.scheduler import select_parallel_batch
from c4harness.integrator import GraphIntegrationSession, detect_conflicts
from c4harness.verifier.executable import execute_checks


class ParallelSafetyRegressionTests(unittest.TestCase):
    def test_parallel_batch_normalizes_absolute_and_relative_write_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            relative = TaskNodeContract(id="a", objective="a", write_paths=(Path("src/a.py"),))
            absolute = TaskNodeContract(
                id="b",
                objective="b",
                write_paths=(repo / "src" / "a.py",),
            )
            batch = select_parallel_batch([relative, absolute], 2, repo=repo)
            self.assertEqual([node.id for node in batch], ["a"])

    def test_out_of_repo_evidence_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            contract = VerificationContract(evidence_requirements=("/tmp/external-proof",))
            result = execute_checks(contract, WorkerResult("success", "done", []), repo)
            self.assertFalse(result.accepted)
            self.assertEqual(result.confidence, "blocked")
            self.assertTrue(any(f.code == "blocked:evidence_requirements" for f in result.failures))

    def test_test_command_source_path_is_rebased_to_integration_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "check.py").write_text("print('ok')\n")
            integration = GraphIntegrationSession.create(
                repo,
                graph_id="graph",
                parent_dir=root / "runs",
            )
            node = TaskNodeContract(
                id="verify",
                objective="verify",
                verification=VerificationContract(
                    deterministic_checks=("tests_pass",),
                    evidence_requirements=(f"test_command:python {repo / 'check.py'}",),
                ),
            )
            translated = GraphExecutionService._node_for_workspace(node, repo, integration)
            command = translated.verification.evidence_requirements[0]
            self.assertIn(str(integration.root / "check.py"), command)
            self.assertNotIn(str(repo / "check.py"), command)

    def test_post_verifier_file_side_effect_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            session = GraphIntegrationSession.create(
                repo,
                graph_id="graph",
                parent_dir=root / "runs",
            )
            patch = root / "proposal.patch"
            patch.write_text(
                "--- /dev/null\n+++ b/result.txt\n@@ -0,0 +1 @@\n+ok\n"
            )
            attempt = session.apply_proposal(
                patch_path=patch,
                write_paths=(repo / "result.txt",),
            )
            self.assertTrue(attempt.accepted)
            (session.root / "rogue.txt").write_text("side effect\n")
            self.assertTrue(session.post_verification_issues(attempt))
            session.rollback(attempt)

    def test_new_source_symlink_is_reported_as_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            session = GraphIntegrationSession.create(
                repo,
                graph_id="graph",
                parent_dir=root / "runs",
            )
            try:
                os.symlink("outside", repo / "new.txt")
            except OSError:
                self.skipTest("symlinks are unavailable")
            conflicts = detect_conflicts(session.snapshot, paths={"new.txt"})
            self.assertTrue(conflicts)
            self.assertIn("symlink", conflicts[0].detail.lower())


if __name__ == "__main__":
    unittest.main()
