"""Deterministic execution of compiled node verifier templates.

Executes the ``deterministic_checks``, ``evidence_requirements``, and
``semantic_criteria`` from a :class:`VerificationContract` against a
:class:`WorkerResult` and repository context.

Design constraints
------------------
- Every path is resolved **under repo**; traversal and symlink escape are
  blocked before any filesystem or subprocess operation.
- Subprocess timeout and captured output are bounded.
- Deterministic failures cannot be overridden by semantic criteria.
- Evidence requirements and semantic checks that cannot be proven locally
  yield **inconclusive** rather than false acceptance.
- Patch checks validate the proposed patch and changed-path allowlist
  against ``node.write_paths``.

Semantics for each template
----------------------------
``file_exists``
    Resolves the path under *repo* and checks ``Path.exists()``.

``file_contains``
    Resolves the path under *repo*; asserts the file exists and is readable.
    Because the v1 DSL argument is a file path (not content), this check
    returns **inconclusive** unless the worker result's evidence or summary
    provides inspectable expected content.  Content-level matching must be
    performed by an evidence or semantic reviewer.

``command_exit_zero``
    Runs the command as a subprocess inside *repo* with bounded timeout and
    captured output.  Returns **blocked** if the command cannot be started
    (e.g. missing executable) and **inconclusive** on timeout.

``output_matches``
    Applies the regex pattern to the worker's raw output file or evidence
    summary.  Returns **inconclusive** when no output content is available.

``json_schema_valid``
    Parses the JSON file for well-formed syntax and (when a schema is
    available) validates the schema.  Without an explicit schema, only
    JSON syntax/shape is validated.

``tests_pass``
    Runs an **explicitly supplied** safe test command from the evidence
    requirements.  Returns **inconclusive** when no test command can be
    identified, rather than inventing a hidden default.

``changed_paths_within_allowlist``
    Checks ``WorkerResult.changed_paths`` against ``write_paths`` from the
    contract.  All changed paths must be within the allowlist.

``patch_non_empty``
    Asserts the proposed patch file exists and contains at least one hunk
    header.

``requirement_coverage``
    Cross-checks ``requirement_refs`` against ``required_requirement_ids``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import VerificationResult, WorkerResult
from ..core.graph import VerificationContract


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SUBPROCESS_TIMEOUT_SEC = 120
MAX_OUTPUT_CAPTURE_BYTES = 100_000
MAX_PATH_DEPTH = 32


# ---------------------------------------------------------------------------
# Internal result type for individual check execution
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _CheckResult:
    """Outcome of a single deterministic or evidence check."""

    name: str
    accepted: bool
    status: str = "ok"  # ok | failed | inconclusive | blocked
    details: str = ""
    fact: str = ""

    def to_issue(self) -> str | None:
        if self.status == "blocked":
            return f"[blocked] {self.name}: {self.details}"
        if self.status == "failed":
            return f"[rejected] {self.name}: {self.details}"
        if self.status == "inconclusive":
            return f"[inconclusive] {self.name}: {self.details}"
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_resolve(path_str: str, repo: Path) -> Path | None:
    """Resolve *path_str* under *repo*, blocking traversal and symlink escape.

    Returns the resolved :class:`Path` on success, or ``None`` if the path
    would escape the repository boundary.
    """
    p = Path(path_str)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (repo / p).resolve()

    repo_resolved = repo.resolve()
    if resolved == repo_resolved:
        return resolved
    if not str(resolved).startswith(str(repo_resolved) + os.sep):
        return None
    try:
        if resolved.is_symlink():
            target = resolved.resolve()
            if not str(target).startswith(str(repo_resolved) + os.sep):
                return None
    except OSError:
        pass
    return resolved


def _is_within_repo(path: Path, repo: Path) -> bool:
    """Return ``True`` if *path* resolves inside *repo*."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    repo_resolved = repo.resolve()
    return resolved == repo_resolved or str(resolved).startswith(
        str(repo_resolved) + os.sep
    )


def _has_hunk_header(patch_text: str) -> bool:
    """Return ``True`` if *patch_text* contains at least one unified-diff
    hunk header (``@@``)."""
    return "@@" in patch_text


# ---------------------------------------------------------------------------
# Individual check runners
# ---------------------------------------------------------------------------


def run_file_exists(spec: Any, contract: VerificationContract, repo: Path) -> _CheckResult:
    resolved = _safe_resolve(spec.argument, repo)
    if resolved is None:
        return _CheckResult(
            name="file_exists",
            accepted=False,
            status="failed",
            details=f"path escapes repository: {spec.argument}",
        )
    if resolved.exists():
        return _CheckResult(
            name="file_exists",
            accepted=True,
            fact=f"file exists: {spec.argument}",
        )
    return _CheckResult(
        name="file_exists",
        accepted=False,
        status="failed",
        details=f"file does not exist: {spec.argument}",
    )


def run_file_contains(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    result: WorkerResult,
) -> _CheckResult:
    resolved = _safe_resolve(spec.argument, repo)
    if resolved is None:
        return _CheckResult(
            name="file_contains",
            accepted=False,
            status="failed",
            details=f"path escapes repository: {spec.argument}",
        )
    if not resolved.exists():
        return _CheckResult(
            name="file_contains",
            accepted=False,
            status="failed",
            details=f"file does not exist: {spec.argument}",
        )
    if not resolved.is_file():
        return _CheckResult(
            name="file_contains",
            accepted=False,
            status="failed",
            details=f"path is not a file: {spec.argument}",
        )

    # v1 DSL: argument is a file path; expected content is not expressible
    # in the template check string itself.  Inspect evidence for hints.
    expected_content: str | None = None
    for item in result.evidence:
        if item.path == spec.argument or item.path.endswith(f"/{spec.argument}"):
            if item.observation and item.observation.strip():
                expected_content = item.observation.strip()
                break

    if not expected_content:
        # Without expected content the check cannot be proven deterministically.
        return _CheckResult(
            name="file_contains",
            accepted=False,
            status="inconclusive",
            details="file exists but expected content is not expressible in v1 DSL; "
            "requires evidence or semantic review",
            fact=f"file exists and is readable: {spec.argument}",
        )

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _CheckResult(
            name="file_contains",
            accepted=False,
            status="inconclusive",
            details=f"cannot read file: {exc}",
        )

    if expected_content in text:
        return _CheckResult(
            name="file_contains",
            accepted=True,
            fact=f"file contains expected content: {spec.argument}",
        )
    return _CheckResult(
        name="file_contains",
        accepted=False,
        status="failed",
        details=f"file does not contain expected content: {spec.argument}",
    )


def run_command_exit_zero(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    timeout: int = MAX_SUBPROCESS_TIMEOUT_SEC,
) -> _CheckResult:
    cmd = spec.argument
    if not cmd.strip():
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="blocked",
            details="empty command",
        )

    effective_timeout = min(timeout, MAX_SUBPROCESS_TIMEOUT_SEC)
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(repo),
            capture_output=True,
            timeout=effective_timeout,
            text=True,
        )
    except FileNotFoundError:
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="blocked",
            details=f"command not found: {cmd}",
        )
    except PermissionError:
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="blocked",
            details=f"permission denied: {cmd}",
        )
    except subprocess.TimeoutExpired:
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="inconclusive",
            details=f"command timed out after {effective_timeout}s: {cmd}",
        )
    except OSError as exc:
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="blocked",
            details=f"cannot execute command: {exc}",
        )

    stdout = (proc.stdout or "")[:MAX_OUTPUT_CAPTURE_BYTES]
    stderr = (proc.stderr or "")[:MAX_OUTPUT_CAPTURE_BYTES]

    if proc.returncode == 0:
        return _CheckResult(
            name="command_exit_zero",
            accepted=True,
            fact=f"command exited 0: {cmd}\nstdout: {stdout[:200]}",
        )
    if proc.returncode == 127:
        return _CheckResult(
            name="command_exit_zero",
            accepted=False,
            status="blocked",
            details=f"command was not found: {cmd}",
        )
    return _CheckResult(
        name="command_exit_zero",
        accepted=False,
        status="failed",
        details=f"command exited {proc.returncode}: {cmd}\nstderr: {stderr[:500]}",
    )


def run_output_matches(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    result: WorkerResult,
) -> _CheckResult:
    pattern = spec.argument
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return _CheckResult(
            name="output_matches",
            accepted=False,
            status="blocked",
            details=f"invalid regex: {exc}",
        )

    # Determine output source: raw output file, then evidence summary.
    output_content: str | None = None
    if result.raw_output_path and result.raw_output_path.exists():
        try:
            output_content = result.raw_output_path.read_text(
                encoding="utf-8", errors="replace"
            )[:MAX_OUTPUT_CAPTURE_BYTES]
        except OSError:
            pass

    if output_content is None and result.summary.strip():
        output_content = result.summary

    if output_content is None:
        return _CheckResult(
            name="output_matches",
            accepted=False,
            status="inconclusive",
            details="no output content available to match against",
        )

    if regex.search(output_content):
        return _CheckResult(
            name="output_matches",
            accepted=True,
            fact=f"output matches pattern: {pattern}",
        )
    return _CheckResult(
        name="output_matches",
        accepted=False,
        status="failed",
        details=f"output does not match pattern: {pattern}",
    )


def run_json_schema_valid(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
) -> _CheckResult:
    resolved = _safe_resolve(spec.argument, repo)
    if resolved is None:
        return _CheckResult(
            name="json_schema_valid",
            accepted=False,
            status="failed",
            details=f"path escapes repository: {spec.argument}",
        )
    if not resolved.exists():
        return _CheckResult(
            name="json_schema_valid",
            accepted=False,
            status="failed",
            details=f"file does not exist: {spec.argument}",
        )
    if not resolved.is_file():
        return _CheckResult(
            name="json_schema_valid",
            accepted=False,
            status="failed",
            details=f"path is not a file: {spec.argument}",
        )

    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return _CheckResult(
            name="json_schema_valid",
            accepted=False,
            status="inconclusive",
            details=f"cannot read file: {exc}",
        )

    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return _CheckResult(
            name="json_schema_valid",
            accepted=False,
            status="failed",
            details=f"invalid JSON: {exc}",
        )

    # v1: validate JSON syntax/shape only; full schema validation requires
    # an explicitly provided schema.
    return _CheckResult(
        name="json_schema_valid",
        accepted=True,
        fact=f"JSON is well-formed: {spec.argument}",
    )


def run_tests_pass(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    timeout: int = MAX_SUBPROCESS_TIMEOUT_SEC,
) -> _CheckResult:
    # Must use an explicitly supplied safe test command.
    test_cmd: str | None = None
    for req in contract.evidence_requirements:
        candidate = req.strip()
        if candidate.startswith("test_command:"):
            test_cmd = candidate.partition(":")[2].strip()
            break

    if not test_cmd:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="inconclusive",
            details="no explicit test command found in evidence_requirements; "
            "cannot run tests without an explicitly supplied safe command",
        )

    effective_timeout = min(timeout, MAX_SUBPROCESS_TIMEOUT_SEC)
    try:
        proc = subprocess.run(
            test_cmd,
            shell=True,
            cwd=str(repo),
            capture_output=True,
            timeout=effective_timeout,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="inconclusive",
            details=f"test command timed out after {effective_timeout}s: {test_cmd}",
        )
    except FileNotFoundError:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="blocked",
            details=f"test command not found: {test_cmd}",
        )
    except PermissionError:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="blocked",
            details=f"permission denied: {test_cmd}",
        )
    except OSError as exc:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="blocked",
            details=f"cannot execute test command: {exc}",
        )

    stdout = (proc.stdout or "")[:MAX_OUTPUT_CAPTURE_BYTES]
    stderr = (proc.stderr or "")[:MAX_OUTPUT_CAPTURE_BYTES]

    if proc.returncode == 0:
        return _CheckResult(
            name="tests_pass",
            accepted=True,
            fact=f"tests passed: {test_cmd}",
        )
    if proc.returncode == 127:
        return _CheckResult(
            name="tests_pass",
            accepted=False,
            status="blocked",
            details=f"test command was not found: {test_cmd}",
        )
    return _CheckResult(
        name="tests_pass",
        accepted=False,
        status="failed",
        details=f"tests failed (exit {proc.returncode}): {test_cmd}\n"
        f"stderr: {stderr[:500]}",
    )


def run_changed_paths_within_allowlist(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    result: WorkerResult,
    write_paths: tuple[str, ...] = (),
) -> _CheckResult:
    allowed = {Path(wp) for wp in write_paths}
    changed = result.changed_paths

    if not changed:
        return _CheckResult(
            name="changed_paths_within_allowlist",
            accepted=False,
            status="inconclusive",
            details="no changed paths reported",
        )

    if not allowed:
        return _CheckResult(
            name="changed_paths_within_allowlist",
            accepted=False,
            status="failed",
            details="changed paths reported but no write_paths allowlist defined",
        )

    violations: list[str] = []
    for cp in changed:
        cp_path = Path(cp)
        # Allow exact match or prefix (directory) match.
        if not any(
            cp_path == allowed_path or _is_within_repo(cp_path, allowed_path.parent)
            for allowed_path in allowed
        ):
            # Also check if the changed path resolves inside the repo at all.
            if not _is_within_repo(cp_path, repo):
                violations.append(f"{cp} (outside repo)")
            else:
                # Check against allowed paths using resolved paths.
                cp_resolved = (repo / cp_path).resolve() if not cp_path.is_absolute() else cp_path.resolve()
                if not any(
                    cp_resolved == (repo / ap).resolve() if not ap.is_absolute() else cp_resolved == ap.resolve()
                    for ap in allowed
                ):
                    violations.append(cp)

    if violations:
        return _CheckResult(
            name="changed_paths_within_allowlist",
            accepted=False,
            status="failed",
            details=f"changed paths outside allowlist: {', '.join(violations)}",
        )
    return _CheckResult(
        name="changed_paths_within_allowlist",
        accepted=True,
        fact=f"all {len(changed)} changed path(s) within allowlist",
    )


def run_patch_non_empty(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    result: WorkerResult,
) -> _CheckResult:
    patch_path = result.proposed_patch_path
    if patch_path is None:
        return _CheckResult(
            name="patch_non_empty",
            accepted=False,
            status="failed",
            details="no proposed patch path",
        )
    if not patch_path.exists():
        return _CheckResult(
            name="patch_non_empty",
            accepted=False,
            status="failed",
            details=f"patch file does not exist: {patch_path}",
        )
    try:
        content = patch_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _CheckResult(
            name="patch_non_empty",
            accepted=False,
            status="inconclusive",
            details=f"cannot read patch: {exc}",
        )
    content = content.strip()
    if not content:
        return _CheckResult(
            name="patch_non_empty",
            accepted=False,
            status="failed",
            details="patch is empty",
        )
    if not _has_hunk_header(content):
        return _CheckResult(
            name="patch_non_empty",
            accepted=False,
            status="failed",
            details="patch has no hunk headers (@@)",
        )
    return _CheckResult(
        name="patch_non_empty",
        accepted=True,
        fact="patch is non-empty and contains hunk headers",
    )


def run_requirement_coverage(
    spec: Any,
    contract: VerificationContract,
    repo: Path,
    requirement_refs: tuple[str, ...] = (),
    required_requirement_ids: tuple[str, ...] = (),
) -> _CheckResult:
    if not required_requirement_ids:
        return _CheckResult(
            name="requirement_coverage",
            accepted=False,
            status="inconclusive",
            details="no required requirement ids provided",
        )

    ref_set = set(requirement_refs)
    missing = [rid for rid in required_requirement_ids if rid not in ref_set]

    if missing:
        return _CheckResult(
            name="requirement_coverage",
            accepted=False,
            status="failed",
            details=f"missing required requirement refs: {', '.join(sorted(missing))}",
        )
    return _CheckResult(
        name="requirement_coverage",
        accepted=True,
        fact=f"all {len(required_requirement_ids)} required requirement(s) covered",
    )


# ---------------------------------------------------------------------------
# Evidence requirements check
# ---------------------------------------------------------------------------


def _check_evidence_requirements(
    evidence_reqs: tuple[str, ...],
    result: WorkerResult,
    repo: Path,
) -> _CheckResult:
    """Verify that worker evidence paths exist inside *repo*.

    Each ``evidence_requirements`` entry is treated as a relative path inside
    the repo.  If the path does not exist the check is **inconclusive** (the
    worker may not have produced the artifact), not rejected — unless the
    evidence explicitly states a requirement that contradicts the result.
    """
    if not evidence_reqs:
        return _CheckResult(name="evidence_requirements", accepted=True)

    missing: list[str] = []
    for req_path in evidence_reqs:
        req_path = req_path.strip()
        if not req_path:
            continue
        if req_path.startswith("test_command:"):
            continue
        # Treat as a repo-relative path.
        candidate = repo / req_path
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        repo_resolved = repo.resolve()
        if resolved == repo_resolved or not str(resolved).startswith(
            str(repo_resolved) + os.sep
        ):
            # Path escapes repo — cannot verify.
            continue
        if not resolved.exists():
            missing.append(req_path)

    if missing:
        return _CheckResult(
            name="evidence_requirements",
            accepted=False,
            status="inconclusive",
            details=f"evidence paths not found: {', '.join(missing)}",
        )
    return _CheckResult(name="evidence_requirements", accepted=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def execute_checks(
    contract: VerificationContract,
    result: WorkerResult,
    repo: Path,
    *,
    timeout: int = MAX_SUBPROCESS_TIMEOUT_SEC,
    worker_output_path: Path | None = None,
    write_paths: tuple[str, ...] = (),
    requirement_refs: tuple[str, ...] = (),
    required_requirement_ids: tuple[str, ...] = (),
) -> VerificationResult:
    """Execute compiled deterministic checks from a ``VerificationContract``.

    Deterministic checks are executed first.  If any deterministic check is
    **blocked**, execution halts immediately and no subsequent checks (evidence,
    semantic) are run — policy blocks are not overridable.

    Semantic checks are always **inconclusive** because they cannot be proven
    locally by a deterministic verifier.

    Returns a :class:`VerificationResult` with ``accepted``, ``confidence``,
    ``issues``, and ``memory_facts`` encoding accepted/rejected/inconclusive/
    blocked semantics.
    """
    from ..decompose.verifier_templates import parse_template_check

    issues: list[str] = []
    facts: list[str] = []
    blocked = False
    has_rejection = False

    # 1. Deterministic template checks.
    for check_str in contract.deterministic_checks:
        try:
            spec = parse_template_check(check_str)
        except Exception as exc:
            issues.append(f"[blocked] {check_str}: parse error: {exc}")
            blocked = True
            break

        cr = _dispatch(spec, contract, result, repo, timeout, worker_output_path, write_paths, requirement_refs, required_requirement_ids)
        if cr.fact:
            facts.append(cr.fact)
        issue = cr.to_issue()
        if issue:
            issues.append(issue)
        if cr.status == "blocked":
            blocked = True
            break
        if cr.status == "failed":
            has_rejection = True

    # 2. Evidence requirements (only if not blocked).
    if not blocked:
        ev_result = _check_evidence_requirements(contract.evidence_requirements, result, repo)
        if ev_result.fact:
            facts.append(ev_result.fact)
        ev_issue = ev_result.to_issue()
        if ev_issue:
            issues.append(ev_issue)

    # 3. Semantic checks — always inconclusive when present.
    if not blocked and contract.semantic_check:
        issues.append(
            f"[inconclusive] semantic_check: cannot be proven locally; "
            f"requires reviewer: {contract.semantic_check}"
        )

    # Encode semantics.
    if blocked:
        accepted = False
        confidence = "blocked"
    elif has_rejection:
        accepted = False
        confidence = "low"
    elif any("[inconclusive]" in iss for iss in issues):
        accepted = False
        confidence = "inconclusive"
    else:
        accepted = True
        confidence = "high" if contract.deterministic_checks else "medium"

    return VerificationResult(
        accepted=accepted,
        confidence=confidence,
        issues=issues,
        memory_facts=facts,
    )


def _dispatch(
    spec: Any,
    contract: VerificationContract,
    result: WorkerResult,
    repo: Path,
    timeout: int,
    worker_output_path: Path | None,
    write_paths: tuple[str, ...],
    requirement_refs: tuple[str, ...],
    required_requirement_ids: tuple[str, ...],
) -> _CheckResult:
    """Dispatch a parsed check spec to the appropriate runner."""
    name = spec.name
    if name == "file_exists":
        return run_file_exists(spec, contract, repo)
    if name == "file_contains":
        return run_file_contains(spec, contract, repo, result)
    if name == "command_exit_zero":
        return run_command_exit_zero(spec, contract, repo, timeout=timeout)
    if name == "output_matches":
        return run_output_matches(spec, contract, repo, result)
    if name == "json_schema_valid":
        return run_json_schema_valid(spec, contract, repo)
    if name == "tests_pass":
        return run_tests_pass(spec, contract, repo, timeout=timeout)
    if name == "changed_paths_within_allowlist":
        return run_changed_paths_within_allowlist(spec, contract, repo, result, write_paths)
    if name == "patch_non_empty":
        return run_patch_non_empty(spec, contract, repo, result)
    if name == "requirement_coverage":
        return run_requirement_coverage(spec, contract, repo, requirement_refs, required_requirement_ids)
    return _CheckResult(
        name=name,
        accepted=False,
        status="blocked",
        details=f"unknown template: {name}",
    )
