"""Tests for verifier-template validation and normalization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.decompose.verifier_templates import (
    PATCH_ONLY_TEMPLATES,
    TemplateCheckSpec,
    TemplateKind,
    TemplateValidationError,
    parse_template_check,
    registered_templates,
    template_kind,
    validate_path_inside_repo,
    validate_template_checks,
)


# ---------------------------------------------------------------------------
# parse_template_check: valid expressions
# ---------------------------------------------------------------------------


class ParseValidTests(unittest.TestCase):
    """All registered templates parse without error on valid inputs."""

    def test_file_exists(self) -> None:
        spec = parse_template_check("file_exists:src/main.py")
        self.assertEqual(spec.name, "file_exists")
        self.assertEqual(spec.argument, "src/main.py")
        self.assertEqual(spec.kind, TemplateKind.FILE_PATH)

    def test_file_contains(self) -> None:
        spec = parse_template_check("file_contains:README.md")
        self.assertEqual(spec.name, "file_contains")
        self.assertEqual(spec.argument, "README.md")

    def test_command_exit_zero(self) -> None:
        spec = parse_template_check("command_exit_zero:make build")
        self.assertEqual(spec.name, "command_exit_zero")
        self.assertEqual(spec.argument, "make build")
        self.assertEqual(spec.kind, TemplateKind.COMMAND)

    def test_output_matches(self) -> None:
        spec = parse_template_check("output_matches:OK\\s*\\d+")
        self.assertEqual(spec.name, "output_matches")
        self.assertEqual(spec.argument, "OK\\s*\\d+")
        self.assertEqual(spec.kind, TemplateKind.PATTERN)

    def test_tests_pass(self) -> None:
        spec = parse_template_check("tests_pass")
        self.assertEqual(spec.name, "tests_pass")
        self.assertEqual(spec.argument, "")
        self.assertEqual(spec.kind, TemplateKind.NONE)

    def test_json_schema_valid(self) -> None:
        spec = parse_template_check("json_schema_valid:schema/config.json")
        self.assertEqual(spec.name, "json_schema_valid")
        self.assertEqual(spec.argument, "schema/config.json")

    def test_changed_paths_within_allowlist(self) -> None:
        spec = parse_template_check("changed_paths_within_allowlist")
        self.assertEqual(spec.name, "changed_paths_within_allowlist")
        self.assertEqual(spec.kind, TemplateKind.NONE)

    def test_patch_non_empty(self) -> None:
        spec = parse_template_check("patch_non_empty")
        self.assertEqual(spec.name, "patch_non_empty")

    def test_requirement_coverage(self) -> None:
        spec = parse_template_check("requirement_coverage")
        self.assertEqual(spec.name, "requirement_coverage")

    def test_argument_with_colons(self) -> None:
        """Argument itself may contain colons (split on first colon only)."""
        spec = parse_template_check("file_contains:data:key:value")
        self.assertEqual(spec.name, "file_contains")
        self.assertEqual(spec.argument, "data:key:value")

    def test_whitespace_stripped(self) -> None:
        spec = parse_template_check("  tests_pass  ")
        self.assertEqual(spec.name, "tests_pass")

    def test_to_string_roundtrip(self) -> None:
        for expr in (
            "file_exists:src/main.py",
            "tests_pass",
            "command_exit_zero:make",
        ):
            spec = parse_template_check(expr)
            self.assertEqual(spec.to_string(), expr.strip())


# ---------------------------------------------------------------------------
# parse_template_check: invalid expressions
# ---------------------------------------------------------------------------


class ParseInvalidTests(unittest.TestCase):
    """Various malformed or invalid expressions are rejected."""

    def test_empty_string(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "empty expression"):
            parse_template_check("")

    def test_whitespace_only(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "empty expression"):
            parse_template_check("   ")

    def test_not_a_string(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "expected string"):
            parse_template_check(42)  # type: ignore[arg-type]

    def test_unknown_template(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unknown template.*magic_check"):
            parse_template_check("magic_check")

    def test_unknown_template_with_arg(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unknown template.*nope"):
            parse_template_check("nope:arg")

    def test_no_arg_template_with_argument(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "takes no argument"):
            parse_template_check("tests_pass:something")

    def test_requires_arg_template_without_argument(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "requires an argument"):
            parse_template_check("file_exists")

    def test_file_path_absolute_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "must be relative"):
            parse_template_check("file_exists:/etc/passwd")

    def test_file_path_traversal_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, r"\.\."):
            parse_template_check("file_exists:../../escape")

    def test_file_path_empty_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "requires an argument"):
            parse_template_check("file_exists: ")

    def test_command_empty_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "requires an argument"):
            parse_template_check("command_exit_zero: ")

    def test_pattern_empty_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "requires an argument"):
            parse_template_check("output_matches: ")

    def test_pattern_invalid_regex_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "invalid regex"):
            parse_template_check("output_matches:([invalid")

    def test_name_with_uppercase_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "invalid template name"):
            parse_template_check("Tests_Pass")

    def test_name_starting_with_digit_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "invalid template name"):
            parse_template_check("1test")

    def test_name_with_hyphen_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "invalid template name"):
            parse_template_check("my-check")

    def test_expression_too_long(self) -> None:
        long_expr = "file_exists:" + "a" * 5000
        with self.assertRaisesRegex(TemplateValidationError, "exceeds maximum length"):
            parse_template_check(long_expr)


# ---------------------------------------------------------------------------
# validate_template_checks: valid scenarios
# ---------------------------------------------------------------------------


class ValidateChecksValidTests(unittest.TestCase):
    """validate_template_checks happy paths."""

    def test_empty_checks_with_contribution_is_valid(self) -> None:
        """Empty checks but non-empty root_contribution passes."""
        result = validate_template_checks(
            (),
            root_contribution="Delivers the feature",
        )
        self.assertEqual(result, ())

    def test_empty_checks_with_evidence_is_valid(self) -> None:
        result = validate_template_checks(
            (),
            evidence_requirements=("output.txt",),
        )
        self.assertEqual(result, ())

    def test_empty_checks_with_semantic_is_valid(self) -> None:
        result = validate_template_checks(
            (),
            semantic_criteria=("Code is idiomatic",),
        )
        self.assertEqual(result, ())

    def test_single_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            result = validate_template_checks(
                ("file_exists:src/main.py",),
                repo_resolved=repo,
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "file_exists")

    def test_multiple_checks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = validate_template_checks(
                ("tests_pass", "requirement_coverage"),
                repo_resolved=repo,
            )
            self.assertEqual(len(result), 2)

    def test_patch_mode_with_explicit_checks(self) -> None:
        result = validate_template_checks(
            ("patch_non_empty", "changed_paths_within_allowlist"),
            execution_mode="patch",
        )
        self.assertEqual(len(result), 2)

    def test_path_checks_validated_against_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            result = validate_template_checks(
                ("file_exists:src/main.py",),
                repo_resolved=repo,
            )
            self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# validate_template_checks: normalization
# ---------------------------------------------------------------------------


class PatchNormalizationTests(unittest.TestCase):
    """Patch-mode normalization adds missing checks."""

    def test_patch_mode_adds_patch_non_empty(self) -> None:
        result = validate_template_checks(
            ("changed_paths_within_allowlist",),
            execution_mode="patch",
        )
        names = {s.name for s in result}
        self.assertIn("patch_non_empty", names)

    def test_patch_mode_adds_changed_paths_within_allowlist(self) -> None:
        result = validate_template_checks(
            ("patch_non_empty",),
            execution_mode="patch",
        )
        names = {s.name for s in result}
        self.assertIn("changed_paths_within_allowlist", names)

    def test_patch_mode_adds_both_when_absent(self) -> None:
        result = validate_template_checks(
            (),
            execution_mode="patch",
            root_contribution="Delivers patch",
        )
        names = {s.name for s in result}
        self.assertIn("patch_non_empty", names)
        self.assertIn("changed_paths_within_allowlist", names)

    def test_patch_mode_does_not_duplicate_existing(self) -> None:
        result = validate_template_checks(
            ("patch_non_empty", "changed_paths_within_allowlist"),
            execution_mode="patch",
        )
        # Each should appear exactly once.
        names = [s.name for s in result]
        self.assertEqual(names.count("patch_non_empty"), 1)
        self.assertEqual(names.count("changed_paths_within_allowlist"), 1)

    def test_read_only_mode_does_not_normalize(self) -> None:
        result = validate_template_checks(
            ("tests_pass",),
            execution_mode="read_only",
        )
        names = {s.name for s in result}
        self.assertNotIn("patch_non_empty", names)
        self.assertNotIn("changed_paths_within_allowlist", names)


# ---------------------------------------------------------------------------
# validate_template_checks: rejection
# ---------------------------------------------------------------------------


class ValidateChecksRejectTests(unittest.TestCase):
    """Invalid inputs are rejected with TemplateValidationError."""

    def test_unknown_template_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unknown template"):
            validate_template_checks(
                ("no_such_template",),
                root_contribution="x",
            )

    def test_duplicate_check_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "duplicate"):
            validate_template_checks(
                ("tests_pass", "tests_pass"),
                root_contribution="x",
            )

    def test_duplicate_check_with_arg_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaisesRegex(TemplateValidationError, "duplicate"):
                validate_template_checks(
                    ("file_exists:a.txt", "file_exists:a.txt"),
                    repo_resolved=repo,
                    root_contribution="x",
                )

    def test_patch_only_in_read_only_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "only valid in patch"):
            validate_template_checks(
                ("patch_non_empty",),
                execution_mode="read_only",
            )

    def test_patch_only_in_execute_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "only valid in patch"):
            validate_template_checks(
                ("changed_paths_within_allowlist",),
                execution_mode="execute",
            )

    def test_absolute_path_in_template_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaisesRegex(TemplateValidationError, "must be relative"):
                validate_template_checks(
                    ("file_exists:/etc/passwd",),
                    repo_resolved=repo,
                    root_contribution="x",
                )

    def test_path_outside_repo_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaisesRegex(TemplateValidationError, "traversal"):
                validate_template_checks(
                    ("file_exists:../../escape",),
                    repo_resolved=repo,
                    root_contribution="x",
                )

    def test_empty_checks_without_any_verifiable_rejected(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unverifiable"):
            validate_template_checks(())

    def test_path_template_without_repo_still_validates_syntax(self) -> None:
        """Without repo_resolved, path templates parse but skip repo check."""
        # This should still fail because path is absolute.
        with self.assertRaisesRegex(TemplateValidationError, "must be relative"):
            validate_template_checks(
                ("file_exists:/abs/path",),
                root_contribution="x",
            )


# ---------------------------------------------------------------------------
# Unverifiable node detection
# ---------------------------------------------------------------------------


class UnverifiableTests(unittest.TestCase):
    """Nodes with no verification signal are rejected."""

    def test_all_empty_raises(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unverifiable"):
            validate_template_checks(
                (),
                root_contribution="",
                evidence_requirements=(),
                semantic_criteria=(),
            )

    def test_whitespace_only_contribution_raises(self) -> None:
        with self.assertRaisesRegex(TemplateValidationError, "unverifiable"):
            validate_template_checks(
                (),
                root_contribution="   ",
                evidence_requirements=(),
                semantic_criteria=(),
            )

    def test_checks_only_is_verifiable(self) -> None:
        result = validate_template_checks(("tests_pass",))
        self.assertEqual(len(result), 1)

    def test_evidence_only_is_verifiable(self) -> None:
        result = validate_template_checks(
            (),
            evidence_requirements=("output.log",),
        )
        self.assertEqual(result, ())

    def test_semantic_only_is_verifiable(self) -> None:
        result = validate_template_checks(
            (),
            semantic_criteria=("Code is clean",),
        )
        self.assertEqual(result, ())

    def test_contribution_only_is_verifiable(self) -> None:
        result = validate_template_checks(
            (),
            root_contribution="Delivers the feature",
        )
        self.assertEqual(result, ())


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


class PathInsideRepoTests(unittest.TestCase):
    """validate_path_inside_repo edge cases."""

    def test_relative_path_inside_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            validate_path_inside_repo("src/main.py", repo)

    def test_relative_path_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(TemplateValidationError):
                validate_path_inside_repo("../../escape", repo)

    def test_absolute_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(TemplateValidationError):
                validate_path_inside_repo("/etc/passwd", repo)

    def test_empty_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(TemplateValidationError):
                validate_path_inside_repo("", repo)

    def test_context_in_error_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaisesRegex(TemplateValidationError, "my_context"):
                validate_path_inside_repo("../../escape", repo, context="my_context")


# ---------------------------------------------------------------------------
# Registered templates and template_kind
# ---------------------------------------------------------------------------


class RegistryTests(unittest.TestCase):
    """Template registry is complete and correct."""

    def test_all_expected_templates_registered(self) -> None:
        expected = {
            "file_exists",
            "file_contains",
            "command_exit_zero",
            "output_matches",
            "tests_pass",
            "json_schema_valid",
            "changed_paths_within_allowlist",
            "patch_non_empty",
            "requirement_coverage",
        }
        self.assertEqual(set(registered_templates()), expected)

    def test_registered_templates_sorted(self) -> None:
        names = registered_templates()
        self.assertEqual(names, sorted(names))

    def test_template_kind_file_path(self) -> None:
        self.assertEqual(template_kind("file_exists"), TemplateKind.FILE_PATH)
        self.assertEqual(template_kind("file_contains"), TemplateKind.FILE_PATH)
        self.assertEqual(template_kind("json_schema_valid"), TemplateKind.FILE_PATH)

    def test_template_kind_command(self) -> None:
        self.assertEqual(template_kind("command_exit_zero"), TemplateKind.COMMAND)

    def test_template_kind_pattern(self) -> None:
        self.assertEqual(template_kind("output_matches"), TemplateKind.PATTERN)

    def test_template_kind_none(self) -> None:
        self.assertEqual(template_kind("tests_pass"), TemplateKind.NONE)
        self.assertEqual(template_kind("patch_non_empty"), TemplateKind.NONE)
        self.assertEqual(template_kind("requirement_coverage"), TemplateKind.NONE)

    def test_unknown_template_kind_raises(self) -> None:
        with self.assertRaises(KeyError):
            template_kind("nonexistent")

    def test_patch_only_set_complete(self) -> None:
        self.assertEqual(
            PATCH_ONLY_TEMPLATES,
            {"patch_non_empty", "changed_paths_within_allowlist"},
        )


# ---------------------------------------------------------------------------
# TemplateCheckSpec dataclass
# ---------------------------------------------------------------------------


class SpecTests(unittest.TestCase):
    """TemplateCheckSpec behaviour."""

    def test_to_string_no_arg(self) -> None:
        spec = TemplateCheckSpec(name="tests_pass", argument="", kind=TemplateKind.NONE)
        self.assertEqual(spec.to_string(), "tests_pass")

    def test_to_string_with_arg(self) -> None:
        spec = TemplateCheckSpec(
            name="file_exists",
            argument="src/main.py",
            kind=TemplateKind.FILE_PATH,
        )
        self.assertEqual(spec.to_string(), "file_exists:src/main.py")

    def test_frozen(self) -> None:
        spec = TemplateCheckSpec(name="tests_pass")
        with self.assertRaises(AttributeError):
            spec.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: full validate_template_checks with patch normalization
# ---------------------------------------------------------------------------


class IntegrationTests(unittest.TestCase):
    """End-to-end scenarios combining parsing, validation, and normalization."""

    def test_read_only_node_with_file_and_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            result = validate_template_checks(
                (
                    "file_exists:src/main.py",
                    "file_contains:src/main.py",
                    "tests_pass",
                ),
                execution_mode="read_only",
                repo_resolved=repo,
            )
            self.assertEqual(len(result), 3)
            names = [s.name for s in result]
            self.assertIn("file_exists", names)
            self.assertIn("file_contains", names)
            self.assertIn("tests_pass", names)

    def test_patch_node_gets_normalized_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            result = validate_template_checks(
                ("file_exists:src/main.py",),
                execution_mode="patch",
                repo_resolved=repo,
                root_contribution="Delivers patch",
            )
            names = {s.name for s in result}
            self.assertIn("patch_non_empty", names)
            self.assertIn("changed_paths_within_allowlist", names)
            self.assertIn("file_exists", names)

    def test_patch_node_with_explicit_checks_not_duplicated(self) -> None:
        result = validate_template_checks(
            ("patch_non_empty", "changed_paths_within_allowlist", "tests_pass"),
            execution_mode="patch",
            root_contribution="Delivers",
        )
        names = [s.name for s in result]
        self.assertEqual(names.count("patch_non_empty"), 1)
        self.assertEqual(names.count("changed_paths_within_allowlist"), 1)
        self.assertEqual(names.count("tests_pass"), 1)
        self.assertEqual(len(result), 3)

    def test_output_matches_with_complex_pattern(self) -> None:
        result = validate_template_checks(
            ("output_matches:^status:\\s+OK$",),
            root_contribution="Checks status",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].argument, "^status:\\s+OK$")

    def test_command_exit_zero_with_pipe(self) -> None:
        result = validate_template_checks(
            ("command_exit_zero:make test | tail -5",),
            root_contribution="Runs tests",
        )
        self.assertEqual(len(result), 1)
        self.assertIn("make test", result[0].argument)


if __name__ == "__main__":
    unittest.main()
