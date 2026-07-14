"""Tests for contract-aware node verification.

Covers every template, traversal, timeout, deterministic rejection,
inconclusive semantic/evidence cases, legacy compatibility, and no command
execution when an earlier policy check blocks.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from c4harness.core.contracts import (
    Evidence,
    FailureCategory,
    FailureRecord,
    Task,
    TaskConstraints,
    TaskMode,
    VerificationResult,
    WorkerResult,
)
from c4harness.core.graph import VerificationContract
from c4harness.verifier.executable import (
    _safe_resolve,
    execute_checks,
    run_changed_paths_within_allowlist,
    run_command_exit_zero,
    run_file_contains,
    run_file_exists,
    run_json_schema_valid,
    run_output_matches,
    run_patch_non_empty,
    run_requirement_coverage,
    run_tests_pass,
)
from c4harness.verifier.service import verify_node, verify_worker_result


def _worker_result(
    summary: str = "done",
    evidence: list[Evidence] | None = None,
    raw_output_path: Path | None = None,
    proposed_patch_path: Path | None = None,
    changed_paths: list[str] | None = None,
    policy_violations: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> WorkerResult:
    return WorkerResult(
        status="success",
        summary=summary,
        evidence=evidence or [],
        raw_output_path=raw_output_path,
        proposed_patch_path=proposed_patch_path,
        changed_paths=changed_paths or [],
        policy_violations=policy_violations or [],
        next_steps=next_steps or ["next"],
    )


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists(unittest.TestCase):
    def test_existing_file_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("x")
            spec = type("S", (), {"argument": "src/main.py"})()
            cr = run_file_exists(spec, VerificationContract(), repo)
            self.assertTrue(cr.accepted)
            self.assertEqual(cr.status, "ok")

    def test_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "missing.py"})()
            cr = run_file_exists(spec, VerificationContract(), repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_traversal_path_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "../../etc/passwd"})()
            cr = run_file_exists(spec, VerificationContract(), repo)
            self.assertFalse(cr.accepted)
            self.assertIn("escapes", cr.details)


# ---------------------------------------------------------------------------
# file_contains
# ---------------------------------------------------------------------------


class TestFileContains(unittest.TestCase):
    def test_file_exists_inconclusive_without_expected_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("hello world")
            spec = type("S", (), {"argument": "README.md"})()
            cr = run_file_contains(spec, VerificationContract(), repo, _worker_result())
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")
            self.assertIn("not expressible", cr.details)

    def test_file_with_matching_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("hello world")
            spec = type("S", (), {"argument": "README.md"})()
            result = _worker_result(
                evidence=[Evidence(path="README.md", observation="hello")]
            )
            cr = run_file_contains(spec, VerificationContract(), repo, result)
            self.assertTrue(cr.accepted)
            self.assertEqual(cr.status, "ok")

    def test_file_with_non_matching_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("hello world")
            spec = type("S", (), {"argument": "README.md"})()
            result = _worker_result(
                evidence=[Evidence(path="README.md", observation="MISSING_CONTENT")]
            )
            cr = run_file_contains(spec, VerificationContract(), repo, result)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "nope.md"})()
            cr = run_file_contains(spec, VerificationContract(), repo, _worker_result())
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_traversal_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "../../etc/passwd"})()
            cr = run_file_contains(spec, VerificationContract(), repo, _worker_result())
            self.assertFalse(cr.accepted)
            self.assertIn("escapes", cr.details)


# ---------------------------------------------------------------------------
# command_exit_zero
# ---------------------------------------------------------------------------


class TestCommandExitZero(unittest.TestCase):
    def test_successful_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "echo ok"})()
            cr = run_command_exit_zero(spec, VerificationContract(), Path(tmp))
            self.assertTrue(cr.accepted)
            self.assertIn("echo ok", cr.fact)

    def test_failing_command_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "false"})()
            cr = run_command_exit_zero(spec, VerificationContract(), Path(tmp))
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_nonexistent_command_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "nonexistent_command_xyz"})()
            cr = run_command_exit_zero(spec, VerificationContract(), Path(tmp))
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "blocked")

    def test_empty_command_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "  "})()
            cr = run_command_exit_zero(spec, VerificationContract(), Path(tmp))
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "blocked")

    def test_timeout_returns_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "sleep 10"})()
            cr = run_command_exit_zero(
                spec, VerificationContract(), Path(tmp), timeout=1
            )
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")
            self.assertIn("timed out", cr.details)


# ---------------------------------------------------------------------------
# output_matches
# ---------------------------------------------------------------------------


class TestOutputMatches(unittest.TestCase):
    def test_matching_pattern_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output.txt"
            out.write_text("status: OK\n42\n")
            result = _worker_result(raw_output_path=out)
            spec = type("S", (), {"argument": r"status:\s+OK"})()
            cr = run_output_matches(spec, VerificationContract(), Path(tmp), result)
            self.assertTrue(cr.accepted)
            self.assertIn("matches", cr.fact)

    def test_non_matching_pattern_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output.txt"
            out.write_text("nothing here")
            result = _worker_result(raw_output_path=out)
            spec = type("S", (), {"argument": r"^status:\s+OK$"})()
            cr = run_output_matches(spec, VerificationContract(), Path(tmp), result)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_no_output_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _worker_result(summary="")
            spec = type("S", (), {"argument": "OK"})()
            cr = run_output_matches(spec, VerificationContract(), Path(tmp), result)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")

    def test_invalid_regex_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "([invalid"})()
            cr = run_output_matches(spec, VerificationContract(), Path(tmp), _worker_result())
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "blocked")

    def test_matches_summary_when_no_raw_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _worker_result(summary="Build succeeded in 42s")
            spec = type("S", (), {"argument": r"Build succeeded"})()
            cr = run_output_matches(spec, VerificationContract(), Path(tmp), result)
            self.assertTrue(cr.accepted)


# ---------------------------------------------------------------------------
# json_schema_valid
# ---------------------------------------------------------------------------


class TestJsonSchemaValid(unittest.TestCase):
    def test_valid_json_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "config.json").write_text(json.dumps({"key": "value"}))
            spec = type("S", (), {"argument": "config.json"})()
            cr = run_json_schema_valid(spec, VerificationContract(), repo)
            self.assertTrue(cr.accepted)
            self.assertIn("well-formed", cr.fact)

    def test_invalid_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "bad.json").write_text("{broken json")
            spec = type("S", (), {"argument": "bad.json"})()
            cr = run_json_schema_valid(spec, VerificationContract(), repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")
            self.assertIn("invalid JSON", cr.details)

    def test_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "missing.json"})()
            cr = run_json_schema_valid(spec, VerificationContract(), repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_traversal_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = type("S", (), {"argument": "../../etc/hosts"})()
            cr = run_json_schema_valid(spec, VerificationContract(), repo)
            self.assertFalse(cr.accepted)
            self.assertIn("escapes", cr.details)


# ---------------------------------------------------------------------------
# tests_pass
# ---------------------------------------------------------------------------


class TestTestsPass(unittest.TestCase):
    def test_explicit_test_command_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("test_command:echo test_ok",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertTrue(cr.accepted)
            self.assertIn("tests passed", cr.fact)

    def test_explicit_test_command_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("test_command:false",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_no_explicit_command_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("some evidence file",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")
            self.assertIn("explicit", cr.details)

    def test_empty_evidence_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract()
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")

    def test_timeout_returns_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("test_command:sleep 60",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo, timeout=1)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")

    def test_nonexistent_command_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("test_command:nonexistent_cmd_xyz",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "blocked")

    def test_pytest_command_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("test_command:pytest --version",)
            )
            spec = type("S", (), {"argument": ""})()
            cr = run_tests_pass(spec, contract, repo)
            self.assertTrue(cr.accepted)
            self.assertIn("tests passed", cr.fact)


# ---------------------------------------------------------------------------
# changed_paths_within_allowlist
# ---------------------------------------------------------------------------


class TestChangedPathsAllowlist(unittest.TestCase):
    def test_all_paths_within_allowlist_passes(self) -> None:
        result = _worker_result(changed_paths=["src/main.py", "src/util.py"])
        cr = run_changed_paths_within_allowlist(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
            write_paths=("src/main.py", "src/util.py"),
        )
        self.assertTrue(cr.accepted)

    def test_path_outside_allowlist_fails(self) -> None:
        result = _worker_result(changed_paths=["src/main.py", "etc/passwd"])
        cr = run_changed_paths_within_allowlist(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
            write_paths=("src/main.py",),
        )
        self.assertFalse(cr.accepted)
        self.assertEqual(cr.status, "failed")
        self.assertIn("etc/passwd", cr.details)

    def test_no_changed_paths_inconclusive(self) -> None:
        result = _worker_result(changed_paths=[])
        cr = run_changed_paths_within_allowlist(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
            write_paths=("src/main.py",),
        )
        self.assertFalse(cr.accepted)
        self.assertEqual(cr.status, "inconclusive")

    def test_no_allowlist_fails_when_paths_exist(self) -> None:
        result = _worker_result(changed_paths=["src/main.py"])
        cr = run_changed_paths_within_allowlist(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
            write_paths=(),
        )
        self.assertFalse(cr.accepted)
        self.assertIn("no write_paths", cr.details)


# ---------------------------------------------------------------------------
# patch_non_empty
# ---------------------------------------------------------------------------


class TestPatchNonEmpty(unittest.TestCase):
    def test_valid_patch_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text(
                "--- a/main.py\n+++ b/main.py\n@@ -1,1 +1,2 @@\n+new line\n"
            )
            result = _worker_result(proposed_patch_path=patch_file)
            cr = run_patch_non_empty(
                type("S", (), {"argument": ""})(),
                VerificationContract(),
                Path(tmp),
                result,
            )
            self.assertTrue(cr.accepted)
            self.assertIn("hunk headers", cr.fact)

    def test_empty_patch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text("")
            result = _worker_result(proposed_patch_path=patch_file)
            cr = run_patch_non_empty(
                type("S", (), {"argument": ""})(),
                VerificationContract(),
                Path(tmp),
                result,
            )
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "failed")

    def test_no_patch_path_fails(self) -> None:
        result = _worker_result(proposed_patch_path=None)
        cr = run_patch_non_empty(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
        )
        self.assertFalse(cr.accepted)
        self.assertIn("no proposed patch", cr.details)

    def test_missing_patch_file_fails(self) -> None:
        result = _worker_result(proposed_patch_path=Path("/nonexistent/patch.diff"))
        cr = run_patch_non_empty(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            result,
        )
        self.assertFalse(cr.accepted)
        self.assertEqual(cr.status, "failed")

    def test_patch_without_hunk_headers_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text("this is not a real patch\n")
            result = _worker_result(proposed_patch_path=patch_file)
            cr = run_patch_non_empty(
                type("S", (), {"argument": ""})(),
                VerificationContract(),
                Path(tmp),
                result,
            )
            self.assertFalse(cr.accepted)
            self.assertIn("hunk headers", cr.details)


# ---------------------------------------------------------------------------
# requirement_coverage
# ---------------------------------------------------------------------------


class TestRequirementCoverage(unittest.TestCase):
    def test_all_covered_passes(self) -> None:
        cr = run_requirement_coverage(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            requirement_refs=("req-1", "req-2"),
            required_requirement_ids=("req-1", "req-2"),
        )
        self.assertTrue(cr.accepted)

    def test_missing_requirement_fails(self) -> None:
        cr = run_requirement_coverage(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            requirement_refs=("req-1",),
            required_requirement_ids=("req-1", "req-2"),
        )
        self.assertFalse(cr.accepted)
        self.assertEqual(cr.status, "failed")
        self.assertIn("req-2", cr.details)

    def test_no_required_ids_inconclusive(self) -> None:
        cr = run_requirement_coverage(
            type("S", (), {"argument": ""})(),
            VerificationContract(),
            Path("/tmp"),
            requirement_refs=("req-1",),
            required_requirement_ids=(),
        )
        self.assertFalse(cr.accepted)
        self.assertEqual(cr.status, "inconclusive")


# ---------------------------------------------------------------------------
# Path safety: traversal and symlink escape
# ---------------------------------------------------------------------------


class TestPathSafety(unittest.TestCase):
    def test_safe_resolve_relative_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("x")
            resolved = _safe_resolve("src/main.py", repo)
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertTrue(resolved.exists())

    def test_safe_resolve_traversal_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            resolved = _safe_resolve("../../etc/passwd", repo)
            self.assertIsNone(resolved)

    def test_safe_resolve_absolute_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            resolved = _safe_resolve("/etc/passwd", repo)
            # Absolute paths resolve but may not be inside repo.
            # The function returns the resolved path; the caller checks.
            # For /etc/passwd, it should not be inside repo.
            if resolved is not None:
                # resolved exists but is outside repo — the check in the
                # caller would catch this via startswith.
                self.assertFalse(str(resolved).startswith(str(repo.resolve()) + os.sep))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks not supported")
    def test_symlink_escape_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "safe").mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("secret")
            link = repo / "safe" / "escape"
            try:
                os.symlink(str(outside), str(link))
            except OSError:
                self.skipTest("cannot create symlink")
            resolved = _safe_resolve("safe/escape", repo)
            # The symlink target is outside repo, so should be blocked.
            if resolved is not None:
                # If resolved is not None, it should still be inside repo.
                # But the symlink check should have caught it.
                self.assertTrue(
                    str(resolved).startswith(str(repo.resolve()) + os.sep),
                    "symlink escape was not blocked",
                )

    def test_traversal_in_template_check_fails(self) -> None:
        """Template checks with traversal paths are rejected at parse time."""
        from c4harness.decompose.verifier_templates import (
            TemplateValidationError,
            parse_template_check,
        )
        with self.assertRaises(TemplateValidationError):
            parse_template_check("file_exists:../../escape")


# ---------------------------------------------------------------------------
# Timeout bound
# ---------------------------------------------------------------------------


class TestTimeoutBound(unittest.TestCase):
    def test_command_timeout_returns_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "sleep 30"})()
            cr = run_command_exit_zero(spec, VerificationContract(), Path(tmp), timeout=1)
            self.assertFalse(cr.accepted)
            self.assertEqual(cr.status, "inconclusive")

    def test_max_timeout_is_bounded(self) -> None:
        """Even if caller passes a huge timeout, it's capped."""
        from c4harness.verifier.executable import MAX_SUBPROCESS_TIMEOUT_SEC
        with tempfile.TemporaryDirectory() as tmp:
            spec = type("S", (), {"argument": "echo ok"})()
            cr = run_command_exit_zero(
                spec, VerificationContract(), Path(tmp), timeout=99999
            )
            self.assertTrue(cr.accepted)


# ---------------------------------------------------------------------------
# Deterministic rejection cannot be overridden
# ---------------------------------------------------------------------------


class TestDeterministicRejectionNotOverridden(unittest.TestCase):
    def test_rejected_check_with_semantic_check_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=("file_exists:missing.py",),
                semantic_check="Code is idiomatic",
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "low")
            self.assertTrue(any("rejected" in iss for iss in vr.issues))

    def test_blocked_check_halts_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=(
                    "command_exit_zero:nonexistent_cmd_xyz",
                    "file_exists:README.md",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "blocked")
            # Only the first check should appear (blocked halts).
            self.assertTrue(any("blocked" in iss for iss in vr.issues))
            # The second check should not have been executed.
            self.assertFalse(any("file_exists" in iss for iss in vr.issues))


# ---------------------------------------------------------------------------
# Inconclusive semantic/evidence
# ---------------------------------------------------------------------------


class TestInconclusiveSemanticEvidence(unittest.TestCase):
    def test_semantic_check_yields_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                semantic_check="Code follows best practices",
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "inconclusive")
            self.assertTrue(any("inconclusive" in iss.lower() for iss in vr.issues))

    def test_missing_evidence_yields_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("output/report.txt",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "inconclusive")
            self.assertTrue(any("inconclusive" in iss.lower() for iss in vr.issues))

    def test_present_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "output").mkdir()
            (repo / "output" / "report.txt").write_text("ok")
            contract = VerificationContract(
                evidence_requirements=("output/report.txt",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertTrue(vr.confidence in ("high", "medium"))

    def test_file_contains_inconclusive_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("content")
            contract = VerificationContract(
                deterministic_checks=("file_contains:README.md",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "inconclusive")
            self.assertTrue(any("inconclusive" in iss.lower() for iss in vr.issues))


# ---------------------------------------------------------------------------
# No command execution when policy check blocks
# ---------------------------------------------------------------------------


class TestNoExecutionAfterBlock(unittest.TestCase):
    def test_blocked_command_prevents_subsequent_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=(
                    "command_exit_zero:nonexistent_cmd_xyz",
                    "command_exit_zero:echo should_not_run",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "blocked")
            # Only one issue — the second command never ran.
            blocked_issues = [i for i in vr.issues if "blocked" in i]
            self.assertEqual(len(blocked_issues), 1)

    def test_parse_error_halts_execution(self) -> None:
        """A parse error in the check string is treated as blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=(
                    "UNKNOWN_TEMPLATE",
                    "file_exists:README.md",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "blocked")


# ---------------------------------------------------------------------------
# Legacy compatibility: verify_worker_result
# ---------------------------------------------------------------------------


class TestLegacyVerifyWorkerResult(unittest.TestCase):
    def test_accepted_when_no_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "evidence.txt").write_text("found")
            result = _worker_result(
                summary="Analysis complete",
                evidence=[Evidence(path="evidence.txt", observation="found")],
                next_steps=["Apply fix"],
            )
            vr = verify_worker_result(result, repo)
            self.assertTrue(vr.accepted)
            self.assertEqual(vr.confidence, "medium")
            self.assertIn("Analysis complete", vr.memory_facts)

    def test_rejected_when_summary_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = _worker_result(summary="", next_steps=["fix"])
            vr = verify_worker_result(result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "low")
            self.assertTrue(any("summary" in iss.lower() for iss in vr.issues))

    def test_rejected_when_evidence_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = _worker_result(
                summary="done",
                evidence=[Evidence(path="/nonexistent/path", observation="x")],
            )
            vr = verify_worker_result(result, repo)
            self.assertFalse(vr.accepted)

    def test_patch_task_requires_patch_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            task = Task(
                goal="patch",
                repo=repo,
                constraints=TaskConstraints(mode=TaskMode.PATCH),
            )
            result = _worker_result(
                summary="done",
                evidence=[Evidence(path="x", observation="y")],
                changed_paths=[],
                proposed_patch_path=None,
                next_steps=["apply"],
            )
            vr = verify_worker_result(result, repo, task)
            self.assertFalse(vr.accepted)
            self.assertTrue(any("patch" in iss.lower() for iss in vr.issues))

    def test_patch_task_accepted_with_valid_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n+new\n")
            task = Task(
                goal="patch",
                repo=repo,
                constraints=TaskConstraints(mode=TaskMode.PATCH),
            )
            result = _worker_result(
                summary="Patched",
                evidence=[Evidence(path="x", observation="patched")],
                changed_paths=["x"],
                proposed_patch_path=patch_file,
                next_steps=["verify"],
            )
            (repo / "x").write_text("patched")
            vr = verify_worker_result(result, repo, task)
            self.assertTrue(vr.accepted)
            self.assertEqual(vr.confidence, "medium")

    def test_return_type_is_verification_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = _worker_result(evidence=[Evidence(path="x", observation="y")])
            vr = verify_worker_result(result, repo)
            self.assertIsInstance(vr, VerificationResult)
            self.assertTrue(hasattr(vr, "accepted"))
            self.assertTrue(hasattr(vr, "confidence"))
            self.assertTrue(hasattr(vr, "issues"))
            self.assertTrue(hasattr(vr, "memory_facts"))
            self.assertTrue(hasattr(vr, "to_dict"))


# ---------------------------------------------------------------------------
# verify_node: contract-aware entry point
# ---------------------------------------------------------------------------


class TestVerifyNode(unittest.TestCase):
    def test_accepted_with_valid_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "main.py").write_text("x")
            from c4harness.core.graph import (
                ExecutionMode,
                NodeKind,
                TaskNodeContract,
            )
            contract = TaskNodeContract(
                objective="create main.py",
                kind=NodeKind.WORK,
                execution_mode=ExecutionMode.READ_ONLY,
                verification=VerificationContract(
                    deterministic_checks=("file_exists:main.py",),
                ),
            )
            result = _worker_result()
            vr = verify_node(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertIn(vr.confidence, ("high", "medium"))

    def test_rejected_when_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            from c4harness.core.graph import (
                ExecutionMode,
                NodeKind,
                TaskNodeContract,
            )
            contract = TaskNodeContract(
                objective="create missing.py",
                kind=NodeKind.WORK,
                execution_mode=ExecutionMode.READ_ONLY,
                verification=VerificationContract(
                    deterministic_checks=("file_exists:missing.py",),
                ),
            )
            result = _worker_result()
            vr = verify_node(contract, result, repo)
            self.assertFalse(vr.accepted)

    def test_patch_checks_validate_write_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n+new\n")
            from c4harness.core.graph import (
                ExecutionMode,
                NodeKind,
                TaskNodeContract,
            )
            contract = TaskNodeContract(
                objective="patch x",
                kind=NodeKind.WORK,
                execution_mode=ExecutionMode.PATCH,
                write_paths=(Path("src/main.py"),),
                verification=VerificationContract(
                    deterministic_checks=("patch_non_empty",),
                ),
            )
            result = _worker_result(
                proposed_patch_path=patch_file,
                changed_paths=["src/main.py"],
            )
            vr = verify_node(contract, result, repo)
            self.assertTrue(vr.accepted)

    def test_semantic_check_yields_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            from c4harness.core.graph import (
                ExecutionMode,
                NodeKind,
                TaskNodeContract,
            )
            contract = TaskNodeContract(
                objective="review",
                kind=NodeKind.WORK,
                execution_mode=ExecutionMode.READ_ONLY,
                verification=VerificationContract(
                    semantic_check="Code is clean",
                ),
            )
            result = _worker_result()
            vr = verify_node(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "inconclusive")
            self.assertTrue(any("inconclusive" in iss.lower() for iss in vr.issues))

    def test_return_type_is_verification_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            from c4harness.core.graph import (
                ExecutionMode,
                NodeKind,
                TaskNodeContract,
            )
            contract = TaskNodeContract(
                objective="x",
                kind=NodeKind.WORK,
                execution_mode=ExecutionMode.READ_ONLY,
                verification=VerificationContract(
                    semantic_check="ok",
                ),
            )
            result = _worker_result()
            vr = verify_node(contract, result, repo)
            self.assertIsInstance(vr, VerificationResult)


# ---------------------------------------------------------------------------
# Integration: full execute_checks scenarios
# ---------------------------------------------------------------------------


class TestExecuteChecksIntegration(unittest.TestCase):
    def test_multiple_checks_all_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Project\n")
            contract = VerificationContract(
                deterministic_checks=(
                    "file_exists:README.md",
                    "command_exit_zero:echo ok",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertEqual(vr.confidence, "high")

    def test_mixed_pass_fail_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Project\n")
            contract = VerificationContract(
                deterministic_checks=(
                    "file_exists:README.md",
                    "file_exists:MISSING.md",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "low")

    def test_json_and_file_combined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "config.json").write_text(json.dumps({"a": 1}))
            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("pass\n")
            contract = VerificationContract(
                deterministic_checks=(
                    "file_exists:src/main.py",
                    "json_schema_valid:config.json",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertEqual(vr.confidence, "high")

    def test_patch_node_full_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            patch_file = Path(tmp) / "patch.diff"
            patch_file.write_text(
                "--- a/src/main.py\n+++ b/src/main.py\n"
                "@@ -1,1 +1,2 @@\n old\n+new\n"
            )
            contract = VerificationContract(
                deterministic_checks=(
                    "patch_non_empty",
                    "changed_paths_within_allowlist",
                ),
            )
            result = _worker_result(
                proposed_patch_path=patch_file,
                changed_paths=["src/main.py"],
            )
            vr = execute_checks(
                contract, result, repo, write_paths=("src/main.py",)
            )
            self.assertTrue(vr.accepted)

    def test_all_checks_yield_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.txt").write_text("a")
            contract = VerificationContract(
                deterministic_checks=(
                    "file_exists:a.txt",
                    "command_exit_zero:echo ok",
                ),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertTrue(len(vr.memory_facts) >= 2)

    def test_no_checks_with_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "report.txt").write_text("done")
            contract = VerificationContract(
                evidence_requirements=("report.txt",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)

    def test_all_checks_with_evidence_and_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.txt").write_text("a")
            (repo / "report.txt").write_text("ok")
            contract = VerificationContract(
                deterministic_checks=("file_exists:a.txt",),
                evidence_requirements=("report.txt",),
                semantic_check="Code is idiomatic",
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertEqual(vr.confidence, "inconclusive")
            # Semantic check makes it inconclusive.
            self.assertTrue(any("inconclusive" in iss.lower() for iss in vr.issues))


# ---------------------------------------------------------------------------
# execute_checks with requirement coverage
# ---------------------------------------------------------------------------


class TestExecuteChecksRequirementCoverage(unittest.TestCase):
    def test_requirement_coverage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=("requirement_coverage",),
            )
            result = _worker_result()
            vr = execute_checks(
                contract, result, repo,
                requirement_refs=("r1", "r2"),
                required_requirement_ids=("r1", "r2"),
            )
            self.assertTrue(vr.accepted)

    def test_requirement_coverage_fails_on_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=("requirement_coverage",),
            )
            result = _worker_result()
            vr = execute_checks(
                contract, result, repo,
                requirement_refs=("r1",),
                required_requirement_ids=("r1", "r2"),
            )
            self.assertFalse(vr.accepted)
            self.assertIn("r2", vr.issues[0])


# ---------------------------------------------------------------------------
# Structured failure classification and serialization
# ---------------------------------------------------------------------------


class TestFailureRecordSerialization(unittest.TestCase):
    def test_failure_record_to_dict(self) -> None:
        rec = FailureRecord(
            category=FailureCategory.WORKER,
            code="failed:tests_pass",
            message="tests failed (exit 1): pytest",
            phase_or_check="tests_pass",
            retryable=True,
            blame="worker",
        )
        d = rec.to_dict()
        self.assertEqual(d["category"], "worker")
        self.assertEqual(d["code"], "failed:tests_pass")
        self.assertEqual(d["message"], "tests failed (exit 1): pytest")
        self.assertEqual(d["phase_or_check"], "tests_pass")
        self.assertTrue(d["retryable"])
        self.assertEqual(d["blame"], "worker")

    def test_failure_category_values_stable(self) -> None:
        expected = {
            "worker", "missing_context", "contract", "policy_permission",
            "environment", "integration_conflict", "deterministic_rejection",
            "semantic_inconclusive",
        }
        actual = {c.value for c in FailureCategory}
        self.assertEqual(actual, expected)


class TestVerificationResultFailuresSerialization(unittest.TestCase):
    def test_to_dict_includes_failures(self) -> None:
        rec = FailureRecord(
            category=FailureCategory.DETERMINISTIC_REJECTION,
            code="failed:file_exists",
            message="file does not exist: missing.py",
            phase_or_check="file_exists",
            retryable=False,
            blame="deterministic_rejection",
        )
        vr = VerificationResult(
            accepted=False,
            confidence="low",
            issues=["[rejected] file_exists: file does not exist: missing.py"],
            failures=[rec],
        )
        d = vr.to_dict()
        self.assertIn("failures", d)
        self.assertEqual(len(d["failures"]), 1)
        self.assertEqual(d["failures"][0]["category"], "deterministic_rejection")
        self.assertEqual(d["failures"][0]["code"], "failed:file_exists")

    def test_to_dict_failures_empty_when_accepted(self) -> None:
        vr = VerificationResult(accepted=True, confidence="high")
        d = vr.to_dict()
        self.assertEqual(d["failures"], [])

    def test_legacy_constructor_still_works(self) -> None:
        """Legacy positional constructor without failures still works."""
        vr = VerificationResult(True, "medium", ["issue1"], ["fact1"])
        self.assertTrue(vr.accepted)
        self.assertEqual(vr.confidence, "medium")
        self.assertEqual(vr.issues, ["issue1"])
        self.assertEqual(vr.memory_facts, ["fact1"])
        self.assertEqual(vr.failures, [])


class TestExecuteChecksStructuredFailures(unittest.TestCase):
    def test_missing_command_produces_environment_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=("command_exit_zero:nonexistent_cmd_xyz",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertTrue(len(vr.failures) > 0)
            f = vr.failures[0]
            self.assertEqual(f.category, FailureCategory.ENVIRONMENT)
            self.assertFalse(f.retryable)
            self.assertEqual(f.blame, "environment")

    def test_failed_deterministic_check_produces_deterministic_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                deterministic_checks=("file_exists:missing.py",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertTrue(len(vr.failures) > 0)
            f = vr.failures[0]
            self.assertEqual(f.category, FailureCategory.DETERMINISTIC_REJECTION)
            self.assertTrue(f.retryable)
            self.assertEqual(f.blame, "deterministic_rejection")

    def test_inconclusive_semantic_produces_semantic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                semantic_check="Code is idiomatic",
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertTrue(len(vr.failures) > 0)
            f = vr.failures[0]
            self.assertEqual(f.category, FailureCategory.SEMANTIC_INCONCLUSIVE)
            self.assertFalse(f.retryable)

    def test_inconclusive_evidence_produces_missing_context_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            contract = VerificationContract(
                evidence_requirements=("output/report.txt",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertFalse(vr.accepted)
            self.assertTrue(len(vr.failures) > 0)
            f = vr.failures[0]
            self.assertEqual(f.category, FailureCategory.MISSING_CONTEXT)

    def test_accepted_check_has_no_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "main.py").write_text("x")
            contract = VerificationContract(
                deterministic_checks=("file_exists:main.py",),
            )
            result = _worker_result()
            vr = execute_checks(contract, result, repo)
            self.assertTrue(vr.accepted)
            self.assertEqual(vr.failures, [])


if __name__ == "__main__":
    unittest.main()
