from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from c4harness.cli import delegation_exit_code, main
from c4harness.core.contracts import VerificationResult, WorkerResult


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


def _multi_node_proposal() -> dict[str, object]:
    """A two-node proposal for testing graph-run with multiple nodes."""
    return {
        "version": 1,
        "root_goal": "Implement and test a feature",
        "requirements": [
            {"id": "R1", "text": "Implement the feature", "kind": "deliverable"},
            {"id": "R2", "text": "Test the feature", "kind": "deliverable"},
        ],
        "constraints": [],
        "acceptance_criteria": [
            {
                "id": "A1",
                "description": "Implementation complete",
                "requirement_refs": ["R1"],
            },
            {
                "id": "A2",
                "description": "Tests pass",
                "requirement_refs": ["R2"],
            },
        ],
        "interaction_mode": "execute",
        "unresolved_questions": [],
        "nodes": [
            {
                "node_id": "implement",
                "objective": "Implement the feature",
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
                "soft_capability_weights": {"code_implementation": 0.8},
                "verifier_plan": {
                    "template_checks": ["requirement_coverage"],
                    "root_contribution": "Satisfies R1",
                },
                "root_contribution": "Satisfies R1",
            },
            {
                "node_id": "test",
                "objective": "Test the feature",
                "kind": "work",
                "requirement_refs": ["R2"],
                "dependencies": ["implement"],
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
                "soft_capability_weights": {"test_generation": 0.8},
                "verifier_plan": {
                    "template_checks": ["requirement_coverage"],
                    "root_contribution": "Satisfies R2",
                },
                "root_contribution": "Satisfies R2",
            },
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


# ---------------------------------------------------------------------------
# graph-run CLI tests
# ---------------------------------------------------------------------------

class TestGraphRunCliDryRun(unittest.TestCase):
    """Test graph-run with dry-run (default, no --execute)."""

    def test_graph_run_dry_run_produces_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
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
            self.assertIn("graph_result", payload)
            gr = payload["graph_result"]
            self.assertTrue(gr["all_succeeded"])
            self.assertEqual(gr["execution_order"], ["review"])
            self.assertFalse(gr["has_failures"])
            self.assertTrue(gr["is_terminal"])

    def test_graph_run_accepts_parent_task_label(self) -> None:
        parser_args = [
            "graph-run",
            "--plan-file",
            "proposal.json",
            "--parent-task-label",
            "parent acceptance",
        ]
        from c4harness.cli import build_parser

        args = build_parser().parse_args(parser_args)
        self.assertEqual(args.parent_task_label, "parent acceptance")

    def test_graph_run_dry_run_human_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
                        "--plan-file",
                        str(proposal_path),
                        "--repo",
                        str(root),
                        "--workers",
                        str(root / "workers.json"),
                        "--memory",
                        str(root / "history.sqlite3"),
                    ]
                )
            self.assertEqual(code, 0)
            text = output.getvalue()
            self.assertIn("Graph Execution", text)
            self.assertIn("All succeeded: True", text)
            self.assertIn("Dry run only", text)

    def test_graph_run_multi_node_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_multi_node_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
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
            gr = payload["graph_result"]
            self.assertTrue(gr["all_succeeded"])
            # implement should come before test (dependency)
            order = gr["execution_order"]
            self.assertEqual(len(order), 2)
            self.assertEqual(order[0], "implement")
            self.assertEqual(order[1], "test")


class TestGraphRunCliMaxParallel(unittest.TestCase):
    """Test graph-run --max-parallel validation."""

    def test_max_parallel_zero_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
                        "--plan-file",
                        str(proposal_path),
                        "--repo",
                        str(root),
                        "--workers",
                        str(root / "workers.json"),
                        "--memory",
                        str(root / "history.sqlite3"),
                        "--max-parallel", "0",
                        "--json",
                    ]
                )
            self.assertEqual(code, 2)
            payload = json.loads(output.getvalue())
            self.assertIn("error", payload)
            self.assertIn("max-parallel", payload["error"].lower())

    def test_max_parallel_one_is_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
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

    def test_max_parallel_greater_than_one_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal()), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
                        "--plan-file",
                        str(proposal_path),
                        "--repo",
                        str(root),
                        "--workers",
                        str(root / "workers.json"),
                        "--memory",
                        str(root / "history.sqlite3"),
                        "--max-parallel", "4",
                        "--json",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["graph_result"]["all_succeeded"])


class TestGraphRunCliErrors(unittest.TestCase):
    """Test graph-run error handling."""

    def test_missing_plan_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
                        "--plan-file",
                        str(root / "nonexistent.json"),
                        "--repo",
                        str(root),
                        "--memory",
                        str(root / "history.sqlite3"),
                        "--json",
                    ]
                )
            self.assertEqual(code, 2)
            payload = json.loads(output.getvalue())
            self.assertIn("error", payload)

    def test_invalid_proposal_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "bad.json"
            proposal_path.write_text("{invalid json", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "graph-run",
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
            payload = json.loads(output.getvalue())
            self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
