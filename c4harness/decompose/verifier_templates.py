"""Validation and normalization of verifier template_checks in task proposals.

Parses the ``template_checks: list[str]`` from a VerifierPlan into typed
:class:`TemplateCheckSpec` objects and validates them against repository
context, node execution mode, and verifier-plan completeness.

Grammar
-------
Each template check string uses a minimal ``name:argument`` syntax::

    <template_name>
    <template_name>:<argument>

Templates that require no arguments (``patch_non_empty``,
``requirement_coverage``, ``tests_pass``) must appear without a colon.
Templates that require exactly one argument use ``name:argument`` with
bounded splitting on the *first* colon only (so the argument may itself
contain colons, e.g. ``file_contains:foo::bar``).

Supported templates (first version from docs/decompose.md)
-----------------------------------------------------------
- ``file_exists:<path>`` – path must be a relative, in-repo path.
- ``file_contains:<path>`` – path must be a relative, in-repo path.
- ``command_exit_zero:<command>`` – command must be non-empty.
- ``output_matches:<pattern>`` – regex pattern must be non-empty.
- ``tests_pass`` – no argument; verifies test suite succeeds.
- ``json_schema_valid:<path>`` – path must be a relative, in-repo path.
- ``changed_paths_within_allowlist`` – no argument; patch-mode only.
- ``patch_non_empty`` – no argument; patch-mode only.
- ``requirement_coverage`` – no argument; verifies requirement coverage.

Design constraints
------------------
- Does **not** execute commands or tests.
- Does **not** modify proposal.py; this module is called by compiler.py.
- Deterministic, stdlib-only, no external schema or regex dependencies.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TemplateValidationError(Exception):
    """Raised when a template_checks list contains an invalid expression."""

    def __init__(self, message: str, expression: str = "") -> None:
        self.expression = expression
        prefix = f"[{expression}] " if expression else ""
        super().__init__(f"{prefix}{message}")


# ---------------------------------------------------------------------------
# Template kind enum
# ---------------------------------------------------------------------------


class TemplateKind(str, Enum):
    """Classifies what kind of argument a template expects."""

    FILE_PATH = "file_path"  # relative in-repo path
    COMMAND = "command"  # non-empty command string
    PATTERN = "pattern"  # non-empty regex/pattern string
    NONE = "none"  # no argument


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

# Maps template name -> (TemplateKind, description)
_TEMPLATE_REGISTRY: dict[str, tuple[TemplateKind, str]] = {
    "file_exists": (TemplateKind.FILE_PATH, "Assert a file exists at path"),
    "file_contains": (
        TemplateKind.FILE_PATH,
        "Assert a file at path contains expected content",
    ),
    "command_exit_zero": (
        TemplateKind.COMMAND,
        "Assert a shell command exits with code 0",
    ),
    "output_matches": (
        TemplateKind.PATTERN,
        "Assert command output matches a regex pattern",
    ),
    "tests_pass": (TemplateKind.NONE, "Assert test suite passes"),
    "json_schema_valid": (
        TemplateKind.FILE_PATH,
        "Assert a JSON file at path validates against its schema",
    ),
    "changed_paths_within_allowlist": (
        TemplateKind.NONE,
        "Assert all changed paths are within the write allowlist (patch mode)",
    ),
    "patch_non_empty": (
        TemplateKind.NONE,
        "Assert the patch is non-empty (patch mode)",
    ),
    "requirement_coverage": (
        TemplateKind.NONE,
        "Assert all required requirements are covered",
    ),
}

# Templates that are only valid in patch execution mode.
PATCH_ONLY_TEMPLATES: frozenset[str] = frozenset(
    {"changed_paths_within_allowlist", "patch_non_empty"}
)


# ---------------------------------------------------------------------------
# Parsed check spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TemplateCheckSpec:
    """A parsed, validated template check expression."""

    name: str
    argument: str = ""
    kind: TemplateKind = TemplateKind.NONE

    def to_string(self) -> str:
        """Reconstruct the canonical string representation."""
        if self.argument:
            return f"{self.name}:{self.argument}"
        return self.name


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Maximum length for a single template expression to prevent abuse.
_MAX_EXPRESSION_LEN = 4096

# Valid template name: lowercase alphanumeric + underscores.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_template_check(expr: str) -> TemplateCheckSpec:
    """Parse a single template check expression string into a TemplateCheckSpec.

    Raises :class:`TemplateValidationError` on invalid syntax, unknown
    templates, or malformed arguments.
    """
    if not isinstance(expr, str):
        raise TemplateValidationError(
            f"expected string, got {type(expr).__name__}"
        )

    if len(expr) > _MAX_EXPRESSION_LEN:
        raise TemplateValidationError(
            f"expression exceeds maximum length ({_MAX_EXPRESSION_LEN})"
        )

    expr = expr.strip()
    if not expr:
        raise TemplateValidationError("empty expression")

    # Split on first colon only.
    if ":" in expr:
        name, _, argument = expr.partition(":")
    else:
        name = expr
        argument = ""

    # Validate name format.
    if not _NAME_RE.match(name):
        raise TemplateValidationError(
            f"invalid template name '{name}': must be lowercase "
            "alphanumeric with underscores, starting with a letter"
        )

    # Look up template in registry.
    if name not in _TEMPLATE_REGISTRY:
        valid = ", ".join(sorted(_TEMPLATE_REGISTRY))
        raise TemplateValidationError(
            f"unknown template '{name}' (valid: {valid})"
        )

    kind, _ = _TEMPLATE_REGISTRY[name]

    # Validate argument presence/absence.
    if kind == TemplateKind.NONE:
        if argument:
            raise TemplateValidationError(
                f"template '{name}' takes no argument, but got ':argument'"
            )
    else:
        if not argument:
            raise TemplateValidationError(
                f"template '{name}' requires an argument (kind={kind.value})"
            )
        # Kind-specific argument validation.
        if kind == TemplateKind.FILE_PATH:
            _validate_path_argument(argument, name)
        elif kind == TemplateKind.COMMAND:
            _validate_command_argument(argument, name)
        elif kind == TemplateKind.PATTERN:
            _validate_pattern_argument(argument, name)

    return TemplateCheckSpec(name=name, argument=argument, kind=kind)


def _validate_path_argument(path_str: str, template_name: str) -> None:
    """Reject absolute paths, empty paths, and path-traversal escapes."""
    if not path_str.strip():
        raise TemplateValidationError(
            f"template '{template_name}': path argument must not be empty"
        )
    p = Path(path_str)
    if p.is_absolute():
        raise TemplateValidationError(
            f"template '{template_name}': path must be relative, "
            f"got absolute '{path_str}'"
        )
    # Reject obvious traversal.
    try:
        resolved = Path(os.path.normpath(path_str))
    except (ValueError, OSError):
        raise TemplateValidationError(
            f"template '{template_name}': invalid path '{path_str}'"
        )
    if ".." in resolved.parts:
        raise TemplateValidationError(
            f"template '{template_name}': path must not contain '..' "
            f"traversal components ('{path_str}')"
        )


def _validate_command_argument(cmd: str, template_name: str) -> None:
    """Reject empty commands."""
    if not cmd.strip():
        raise TemplateValidationError(
            f"template '{template_name}': command must not be empty"
        )


def _validate_pattern_argument(pattern: str, template_name: str) -> None:
    """Reject empty patterns and validate regex syntax."""
    if not pattern.strip():
        raise TemplateValidationError(
            f"template '{template_name}': pattern must not be empty"
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise TemplateValidationError(
            f"template '{template_name}': invalid regex pattern: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Path-inside-repo validation (used by compiler wiring)
# ---------------------------------------------------------------------------


def validate_path_inside_repo(
    path_str: str,
    repo_resolved: Path,
    context: str = "",
) -> None:
    """Raise TemplateValidationError if *path_str* resolves outside *repo_resolved*.

    This mirrors compiler._validate_path_inside_repo but raises
    TemplateValidationError so the template module is self-contained.
    """
    if not path_str or not path_str.strip():
        raise TemplateValidationError(
            f"{context}: empty path" if context else "empty path"
        )
    p = Path(path_str)
    resolved = (repo_resolved / p) if not p.is_absolute() else p
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = resolved.absolute()
    repo_str = str(repo_resolved)
    if resolved != repo_resolved and not str(resolved).startswith(
        repo_str + os.sep
    ):
        msg = (
            f"{context}: path '{path_str}' resolves outside repository"
            if context
            else f"path '{path_str}' resolves outside repository"
        )
        raise TemplateValidationError(msg)


# ---------------------------------------------------------------------------
# Validation entry point
# ---------------------------------------------------------------------------


def validate_template_checks(
    checks: tuple[str, ...],
    *,
    execution_mode: str = "read_only",
    write_paths: tuple[str, ...] = (),
    repo_resolved: Path | None = None,
    root_contribution: str = "",
    evidence_requirements: tuple[str, ...] = (),
    semantic_criteria: tuple[str, ...] = (),
) -> tuple[TemplateCheckSpec, ...]:
    """Parse, validate, and normalize a list of template check expressions.

    Performs:
    1. Parse each expression into a TemplateCheckSpec.
    2. Reject duplicate checks (same name + argument).
    3. Reject patch-only templates on non-patch nodes.
    4. For path-argument templates, verify paths are relative and inside repo.
    5. Normalize patch nodes by adding missing patch-only templates.
    6. Validate that the verifier plan is not unverifiable (has at least one
       of: template_checks, evidence_requirements, semantic_criteria, or
       root_contribution).

    Args:
        checks: The raw template_checks strings from the proposal.
        execution_mode: The node's execution_mode value.
        write_paths: The node's write_paths for allowlist validation.
        repo_resolved: The resolved repo root path for path validation.
        root_contribution: The verifier plan's root_contribution string.
        evidence_requirements: The verifier plan's evidence_requirements.
        semantic_criteria: The verifier plan's semantic_criteria.

    Returns:
        A tuple of parsed TemplateCheckSpec objects (possibly augmented
        with normalization additions).

    Raises:
        TemplateValidationError: On any validation failure.
    """
    is_patch = execution_mode == "patch"

    # -- Parse all checks ----------------------------------------------------
    specs: list[TemplateCheckSpec] = []
    seen: set[tuple[str, str]] = set()

    for expr in checks:
        spec = parse_template_check(expr)

        # Duplicate detection.
        key = (spec.name, spec.argument)
        if key in seen:
            raise TemplateValidationError(
                f"duplicate check: '{spec.to_string()}'", expr
            )
        seen.add(key)

        # Patch-only check in non-patch mode.
        if spec.name in PATCH_ONLY_TEMPLATES and not is_patch:
            raise TemplateValidationError(
                f"template '{spec.name}' is only valid in patch execution mode, "
                f"but node execution_mode is '{execution_mode}'",
                expr,
            )

        # Path-argument templates: validate path is inside repo.
        if spec.kind == TemplateKind.FILE_PATH and repo_resolved is not None:
            validate_path_inside_repo(
                spec.argument,
                repo_resolved,
                context=f"template '{spec.name}'",
            )

        specs.append(spec)

    # -- Normalize patch nodes: add missing patch-only checks ----------------
    spec_names = {s.name for s in specs}
    if is_patch:
        additions: list[TemplateCheckSpec] = []
        if "patch_non_empty" not in spec_names:
            additions.append(
                TemplateCheckSpec(
                    name="patch_non_empty",
                    argument="",
                    kind=TemplateKind.NONE,
                )
            )
        if "changed_paths_within_allowlist" not in spec_names:
            additions.append(
                TemplateCheckSpec(
                    name="changed_paths_within_allowlist",
                    argument="",
                    kind=TemplateKind.NONE,
                )
            )
        specs.extend(additions)

    # -- Validate that the node is verifiable --------------------------------
    _assert_verifiable(
        tuple(specs),
        evidence_requirements=evidence_requirements,
        semantic_criteria=semantic_criteria,
        root_contribution=root_contribution,
    )

    return tuple(specs)


def _assert_verifiable(
    specs: tuple[TemplateCheckSpec, ...],
    *,
    evidence_requirements: tuple[str, ...] = (),
    semantic_criteria: tuple[str, ...] = (),
    root_contribution: str = "",
) -> None:
    """Raise if the verifier plan has no way to verify the node."""
    has_checks = bool(specs)
    has_evidence = bool(evidence_requirements)
    has_semantic = bool(semantic_criteria)
    has_contribution = bool(root_contribution.strip())

    if not (has_checks or has_evidence or has_semantic or has_contribution):
        raise TemplateValidationError(
            "verifier plan is unverifiable: no template_checks, "
            "evidence_requirements, semantic_criteria, or root_contribution"
        )


# ---------------------------------------------------------------------------
# Convenience: list all registered template names
# ---------------------------------------------------------------------------


def registered_templates() -> list[str]:
    """Return sorted list of all registered template names."""
    return sorted(_TEMPLATE_REGISTRY)


def template_kind(name: str) -> TemplateKind:
    """Return the TemplateKind for a registered template name.

    Raises KeyError if *name* is not registered.
    """
    return _TEMPLATE_REGISTRY[name][0]
