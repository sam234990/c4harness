from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from cost_router.cli import delegation_exit_code, main
from cost_router.core.contracts import VerificationResult, WorkerResult


def _proposal() -> dict[str, object]:
    return {
        "version": 1,
        "root_goal": "Review the documentation",
        "requirements": [
            {"id": "R1", "text": "Produce a review", "kind": "deliverable"}
        ],
        "constraints": ["Remain read-only"],
        "acceptance_criteria": [
            {
                "id": "A1",
                "description": "Review covers R1",
                "requirement_refs": ["R1"],
            }
        ],
        "interaction_mode": "execute",
        "unresolved_questions": [],
        "nodes": [
            {
                "node_id": "review",
                "objective": "Review the documentation",
                "kind": "work",
                "requirement_refs": ["R1"],
                "dependencies": [],
                "context_packs": [],
                "artifact_inputs": [],
                "allowed_paths": [],
                "write_paths": [],
                "execution_mode": "read_only",
                "output_type": "report",
                "hard_capabilities": {
                    "modalities": ["text"],
                    "tools": ["read"],
                },
                "soft_capability_weights": {"documentation": 0.8},
                "verifier_plan": {
                    "template_checks": ["requirement_coverage"],
                    "root_contribution": "Satisfies R1",
                },
                "root_contribution": "Satisfies R1",
            }
        ],
    }


class DecompositionCliTests(unittest.TestCase):
    def test_plan_file_compiles_without_calling_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "decompose",
                        "--plan-file",
                        str(proposal_path),
                        "--repo",
                        str(root),
                        "--workers",
                        str(root / "workers.json"),
                        "--memory",
                        str(root / "history.sqlite3"),
                        "--json",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["shape"], "fast_path")
            self.assertEqual(payload["graph"]["nodes"][0]["id"], "review")
            self.assertTrue(payload["graph"]["nodes"][0]["assigned_worker_id"])

    def test_invalid_plan_file_returns_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text('{"version": 1}', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "decompose",
                        "--plan-file",
                        str(proposal_path),
                        "--repo",
                        str(root),
                        "--memory",
                        str(root / "history.sqlite3"),
                        "--json",
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("error", json.loads(output.getvalue()))

    def test_delegation_exit_code_reflects_worker_and_verifier_failure(self) -> None:
        accepted = VerificationResult(accepted=True, confidence="medium")
        rejected = VerificationResult(accepted=False, confidence="low")
        success = WorkerResult(status="success", summary="done")
        failed = WorkerResult(status="failed", summary="failed")

        self.assertEqual(delegation_exit_code(False, None, None), 0)
        self.assertEqual(delegation_exit_code(True, success, accepted), 0)
        self.assertEqual(delegation_exit_code(True, failed, rejected), 1)
        self.assertEqual(delegation_exit_code(True, success, rejected), 1)
        self.assertEqual(delegation_exit_code(True, success, None), 1)


if __name__ == "__main__":
    unittest.main()
