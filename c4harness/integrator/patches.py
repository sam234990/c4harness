"""Patch preflight and application primitives.

Applies unified-diff hunks to an :class:`IntegrationSnapshot` with path
allowlist enforcement and atomic replacement.

Design guarantees
-----------------
* **Path allowlist** – every target path must be within the allowed set.
* **Traversal rejection** – paths containing ``..`` or escaping the
  snapshot root are rejected before any I/O.
* **Atomic replacement** – either all hunks in a batch succeed or none
  are applied (all-or-nothing).
* **Text-only** – binary files are rejected; all diff content is UTF-8.
* **Structured results** – :class:`PatchResult` carries per-change
  outcomes; :class:`FileChange` records what happened to each file.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import tempfile
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .workspace import (
    FileState,
    IntegrationSnapshot,
    is_excluded_relative_path,
    normalize_repo_relative,
)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

class ChangeKind(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class PatchHunk:
    """A single change to apply to the snapshot.

    Parameters
    ----------
    path:
        Repo-relative target path (forward-slash separated).
    kind:
        Whether this creates, modifies, or deletes the file.
    content:
        For ``CREATE`` and ``MODIFY``: the new file content as a string.
        For ``DELETE``: ignored (may be ``None``).
    expected_sha256:
        For ``MODIFY``: the SHA-256 the file *must* have before patching.
        For ``CREATE``: must be ``None`` (file must not exist).
        For ``DELETE``: the SHA-256 the file must have before deletion.
    """

    path: str
    kind: ChangeKind
    content: str | None = None
    expected_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "has_content": self.content is not None,
            "expected_sha256": self.expected_sha256,
        }


@dataclass(frozen=True, slots=True)
class FileChange:
    """Record of a single applied change."""

    path: str
    kind: ChangeKind
    old_sha256: str | None
    new_sha256: str | None
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "old_sha256": self.old_sha256,
            "new_sha256": self.new_sha256,
            "size": self.size,
        }


@dataclass(slots=True)
class PatchResult:
    """Outcome of applying a batch of hunks to a snapshot."""

    applied: list[FileChange] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    rollback_dir: Path | None = field(default=None, repr=False)

    @property
    def success(self) -> bool:
        return bool(self.applied) and not self.failed and not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "applied_count": len(self.applied),
            "failed_count": len(self.failed),
            "violation_count": len(self.violations),
            "applied": [c.to_dict() for c in self.applied],
            "failed": self.failed,
            "violations": self.violations,
        }


# ---------------------------------------------------------------------------
# Patch applier
# ---------------------------------------------------------------------------

class PatchApplier:
    """Validates and applies unified-diff hunks to an integration snapshot.

    Usage::

        applier = PatchApplier(snapshot, allowed_paths={"src/main.py", "lib/"})
        result = applier.apply(hunks)

    Parameters
    ----------
    snapshot:
        The snapshot to patch.  Mutated in-place on success.
    allowed_paths:
        Set of repo-relative paths or directory prefixes that the worker
        is allowed to modify.  A path is allowed if it equals an entry in
        the set or is a child of a directory in the set.
    """

    def __init__(
        self,
        snapshot: IntegrationSnapshot,
        allowed_paths: set[str] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._allowed = allowed_paths

    @property
    def snapshot(self) -> IntegrationSnapshot:
        return self._snapshot

    def apply(
        self,
        hunks: list[PatchHunk],
        *,
        retain_rollback: bool = False,
    ) -> PatchResult:
        """Validate all hunks, then apply atomically.

        If any hunk fails validation, **none** are applied and the
        snapshot is left unchanged.
        """
        if self._snapshot.pending_rollback is not None:
            return PatchResult(
                failed=["A previous patch transaction is still awaiting commit or rollback."]
            )
        symlink = _first_symlink(self._snapshot.root)
        if symlink is not None:
            return PatchResult(
                failed=[f"Integration workspace invariant violated by symlink: {symlink}"]
            )

        # Phase 1: validate all hunks and reject duplicate target paths.
        to_apply: list[tuple[PatchHunk, Path, FileState | None]] = []
        failed: list[str] = []
        violations: list[str] = []

        seen: set[str] = set()
        for hunk in hunks:
            ok, dest, old_state, error = self._validate_hunk(hunk)
            if not ok:
                if "violation" in error.lower() or "allowlist" in error.lower():
                    violations.append(error)
                else:
                    failed.append(error)
            else:
                relative = normalize_repo_relative(hunk.path, self._snapshot.root).as_posix()
                if relative in seen:
                    failed.append(f"Duplicate patch target: {relative}")
                    continue
                seen.add(relative)
                to_apply.append((hunk, dest, old_state))

        if failed or violations:
            return PatchResult(failed=failed, violations=violations)

        if not to_apply:
            return PatchResult(failed=["Patch contains no file changes."])

        # Phase 2: build the complete result in a sibling transaction tree.
        # Directory swaps happen on the same filesystem, so either the old
        # graph workspace or the new graph workspace remains addressable.
        transaction_root = Path(
            tempfile.mkdtemp(prefix=f".{self._snapshot.root.name}.txn-", dir=self._snapshot.root.parent)
        )
        shutil.rmtree(transaction_root)
        backup_root = self._snapshot.root.parent / (
            f".{self._snapshot.root.name}.rollback-{uuid4().hex}"
        )
        applied: list[FileChange] = []
        next_states = dict(self._snapshot.file_states)
        try:
            shutil.copytree(self._snapshot.root, transaction_root)
            for hunk, _dest, old_state in to_apply:
                change = self._apply_to_root(hunk, transaction_root, old_state, next_states)
                applied.append(change)
            os.replace(self._snapshot.root, backup_root)
            try:
                os.replace(transaction_root, self._snapshot.root)
            except BaseException:
                os.replace(backup_root, self._snapshot.root)
                raise
        except BaseException as exc:
            shutil.rmtree(transaction_root, ignore_errors=True)
            if backup_root.exists() and not self._snapshot.root.exists():
                os.replace(backup_root, self._snapshot.root)
            return PatchResult(failed=[f"Patch transaction failed: {type(exc).__name__}: {exc}"])

        self._snapshot.file_states = next_states
        result = PatchResult(applied=applied, rollback_dir=backup_root)
        self._snapshot.pending_rollback = backup_root
        if not retain_rollback:
            self.commit(result)
        return result

    def commit(self, result: PatchResult) -> None:
        """Discard a retained pre-patch workspace after post verification."""
        if result.rollback_dir is not None:
            if self._snapshot.pending_rollback != result.rollback_dir:
                raise ValueError("Patch transaction does not own the pending rollback.")
            shutil.rmtree(result.rollback_dir, ignore_errors=True)
            self._snapshot.pending_rollback = None
            result.rollback_dir = None

    def rollback(self, result: PatchResult) -> bool:
        """Restore the retained pre-patch graph workspace."""
        backup = result.rollback_dir
        if backup is None or not backup.exists():
            return False
        if self._snapshot.pending_rollback != backup:
            raise ValueError("Patch transaction does not own the pending rollback.")
        rejected = self._snapshot.root.parent / (
            f".{self._snapshot.root.name}.rejected-{uuid4().hex}"
        )
        os.replace(self._snapshot.root, rejected)
        try:
            os.replace(backup, self._snapshot.root)
        except BaseException:
            os.replace(rejected, self._snapshot.root)
            raise
        shutil.rmtree(rejected, ignore_errors=True)
        self._snapshot.file_states = _scan_file_states(self._snapshot.root)
        self._snapshot.pending_rollback = None
        result.rollback_dir = None
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _validate_hunk(
        self,
        hunk: PatchHunk,
    ) -> tuple[bool, Path, FileState | None, str]:
        """Return ``(ok, dest_path, old_state, error_message)``."""
        # Normalize and reject traversal.
        try:
            relative = normalize_repo_relative(hunk.path, self._snapshot.root)
        except ValueError as exc:
            return False, Path(), None, f"Path rejected: {hunk.path} ({exc})"

        relative_str = relative.as_posix()
        dest = self._snapshot.root / relative

        # Allowlist check.
        if self._allowed is not None:
            if not self._is_allowed(relative_str):
                return (
                    False,
                    dest,
                    None,
                    f"Path outside write allowlist: {relative_str}",
                )

        old_state = self._snapshot.file_states.get(relative_str)

        if hunk.kind == ChangeKind.CREATE:
            if old_state is not None:
                return (
                    False,
                    dest,
                    old_state,
                    f"File already exists (cannot CREATE): {relative_str}",
                )
            if hunk.expected_sha256 is not None:
                return (
                    False,
                    dest,
                    None,
                    f"CREATE must not specify expected_sha256: {relative_str}",
                )
            if hunk.content is None:
                return (
                    False,
                    dest,
                    None,
                    f"CREATE requires content: {relative_str}",
                )

        elif hunk.kind == ChangeKind.MODIFY:
            if old_state is None:
                return (
                    False,
                    dest,
                    None,
                    f"File does not exist (cannot MODIFY): {relative_str}",
                )
            if hunk.content is None:
                return (
                    False,
                    dest,
                    old_state,
                    f"MODIFY requires content: {relative_str}",
                )
            if hunk.expected_sha256 is not None:
                if old_state.sha256 != hunk.expected_sha256:
                    return (
                        False,
                        dest,
                        old_state,
                        f"SHA-256 mismatch for {relative_str}: "
                        f"expected {hunk.expected_sha256[:16]}…, "
                        f"found {old_state.sha256[:16]}…",
                    )

        elif hunk.kind == ChangeKind.DELETE:
            if old_state is None:
                return (
                    False,
                    dest,
                    None,
                    f"File does not exist (cannot DELETE): {relative_str}",
                )
            if hunk.expected_sha256 is not None:
                if old_state.sha256 != hunk.expected_sha256:
                    return (
                        False,
                        dest,
                        old_state,
                        f"SHA-256 mismatch for DELETE {relative_str}: "
                        f"expected {hunk.expected_sha256[:16]}…, "
                        f"found {old_state.sha256[:16]}…",
                    )

        return True, dest, old_state, ""

    def _apply_to_root(
        self,
        hunk: PatchHunk,
        root: Path,
        old_state: FileState | None,
        states: dict[str, FileState],
    ) -> FileChange:
        """Apply a single validated hunk and update the snapshot."""
        relative_str = normalize_repo_relative(
            hunk.path, self._snapshot.root
        ).as_posix()

        dest = root / relative_str
        if hunk.kind == ChangeKind.DELETE:
            if dest.exists():
                dest.unlink()
            states.pop(relative_str, None)
            return FileChange(
                path=relative_str,
                kind=ChangeKind.DELETE,
                old_sha256=old_state.sha256 if old_state else None,
                new_sha256=None,
            )

        # CREATE or MODIFY inside the transaction tree.
        content = hunk.content or ""
        data = content.encode("utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        new_sha = hashlib.sha256(data).hexdigest()
        states[relative_str] = FileState(
            path=relative_str,
            sha256=new_sha,
            size=len(data),
        )
        return FileChange(
            path=relative_str,
            kind=hunk.kind,
            old_sha256=old_state.sha256 if old_state else None,
            new_sha256=new_sha,
            size=len(data),
        )

    def _is_allowed(self, relative_str: str) -> bool:
        """Return ``True`` if *relative_str* is within the allowlist."""
        if self._allowed is None:
            return True
        for allowed in self._allowed:
            if relative_str == allowed:
                return True
            if allowed.endswith("/") and relative_str.startswith(allowed):
                return True
            # Existing directories are scopes; existing files and missing
            # paths are exact targets. This prevents an allowlist entry for
            # a new file (``new.py``) from authorising ``new.py/child``.
            allowed_path = self._snapshot.root / allowed
            if allowed_path.is_dir() and not allowed_path.is_symlink():
                if relative_str.startswith(allowed.rstrip("/") + "/"):
                    return True
        return False

    def apply_unified_diff(
        self,
        patch_path: Path,
        *,
        retain_rollback: bool = False,
    ) -> PatchResult:
        """Parse and apply a C4 text ``proposed.patch`` file."""
        try:
            patch_text = patch_path.read_text(encoding="utf-8")
            hunks = parse_unified_diff(patch_text, self._snapshot)
        except (OSError, UnicodeError, ValueError) as exc:
            return PatchResult(failed=[f"Invalid proposed patch: {exc}"])
        return self.apply(hunks, retain_rollback=retain_rollback)


# ---------------------------------------------------------------------------
# Unified-diff helpers
# ---------------------------------------------------------------------------

def generate_unified_diff(
    label: str,
    old_text: str,
    new_text: str,
    *,
    existed_before: bool = True,
    exists_after: bool = True,
) -> str:
    """Generate a unified-diff string for a single file.

    Parameters
    ----------
    label:
        Repo-relative path label used in diff headers.
    old_text:
        Original file content (empty string if file is new).
    new_text:
        New file content (empty string if file is deleted).
    existed_before:
        Whether the file existed before the change.
    exists_after:
        Whether the file exists after the change.

    Returns
    -------
    str
        Unified-diff text (may be empty if content is identical).
    """
    if old_text == new_text and existed_before == exists_after:
        return ""
    fromfile = f"a/{label}" if existed_before else "/dev/null"
    tofile = f"b/{label}" if exists_after else "/dev/null"
    lines = list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
    ))
    if not lines and existed_before != exists_after:
        return f"--- {fromfile}\n+++ {tofile}\n"
    return _encode_no_newline_markers(lines)


_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


def parse_unified_diff(
    patch_text: str,
    snapshot: IntegrationSnapshot,
) -> list[PatchHunk]:
    """Parse the text-only unified format emitted by C4 patch workers.

    The parser deliberately supports a narrow format: paired ``---``/``+++``
    file headers followed by ordinary unified hunks.  Git binary patches,
    renames, traversal and unmatched context are rejected.
    """
    if not patch_text.strip():
        raise ValueError("patch is empty")
    if "GIT binary patch" in patch_text or "Binary files " in patch_text:
        raise ValueError("binary patches are not supported")
    lines = patch_text.splitlines(keepends=True)
    index = 0
    operations: list[PatchHunk] = []
    while index < len(lines):
        while index < len(lines) and not lines[index].startswith("--- "):
            if lines[index].strip():
                raise ValueError(f"unexpected patch line: {lines[index].rstrip()}")
            index += 1
        if index >= len(lines):
            break
        old_label = lines[index][4:].rstrip("\r\n")
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValueError("missing +++ file header")
        new_label = lines[index][4:].rstrip("\r\n")
        index += 1
        old_path = _header_path(old_label)
        new_path = _header_path(new_label)
        if old_path is None and new_path is None:
            raise ValueError("both patch paths are /dev/null")
        if old_path is not None and new_path is not None and old_path != new_path:
            raise ValueError("renames are not supported")
        relative = old_path or new_path
        assert relative is not None
        normalize_repo_relative(relative, snapshot.root)
        current_path = snapshot.root / relative
        if old_path is None:
            original: list[str] = []
            kind = ChangeKind.CREATE
            expected = None
        else:
            if not current_path.is_file():
                raise ValueError(f"patch source does not exist: {relative}")
            original = current_path.read_text(encoding="utf-8").splitlines(keepends=True)
            kind = ChangeKind.DELETE if new_path is None else ChangeKind.MODIFY
            expected = snapshot.file_states.get(relative)
            if expected is None:
                raise ValueError(f"patch source is not in workspace state: {relative}")
        output: list[str] = []
        source_cursor = 0
        saw_hunk = False
        while index < len(lines) and not lines[index].startswith("--- "):
            header = _HUNK_HEADER.match(lines[index].rstrip("\r\n"))
            if header is None:
                if lines[index].strip():
                    raise ValueError(f"malformed hunk header: {lines[index].rstrip()}")
                index += 1
                continue
            saw_hunk = True
            old_start = int(header.group(1))
            old_count = int(header.group(2) or "1")
            new_count = int(header.group(4) or "1")
            target_cursor = max(0, old_start - 1)
            if target_cursor < source_cursor or target_cursor > len(original):
                raise ValueError(f"invalid hunk offset for {relative}")
            output.extend(original[source_cursor:target_cursor])
            source_cursor = target_cursor
            index += 1
            consumed_old = 0
            produced_new = 0
            while index < len(lines):
                line = lines[index]
                if line.startswith("--- ") or _HUNK_HEADER.match(line.rstrip("\r\n")):
                    break
                if line.startswith("\\ No newline at end of file"):
                    index += 1
                    continue
                prefix = line[:1]
                payload = line[1:]
                no_newline = (
                    index + 1 < len(lines)
                    and lines[index + 1].startswith("\\ No newline at end of file")
                )
                if no_newline:
                    payload = payload.rstrip("\r\n")
                if prefix == " ":
                    if source_cursor >= len(original) or original[source_cursor] != payload:
                        raise ValueError(f"context mismatch for {relative}")
                    output.append(payload)
                    source_cursor += 1
                    consumed_old += 1
                    produced_new += 1
                elif prefix == "-":
                    if source_cursor >= len(original) or original[source_cursor] != payload:
                        raise ValueError(f"deletion mismatch for {relative}")
                    source_cursor += 1
                    consumed_old += 1
                elif prefix == "+":
                    output.append(payload)
                    produced_new += 1
                else:
                    raise ValueError(f"invalid hunk line for {relative}")
                index += 2 if no_newline else 1
            if consumed_old != old_count or produced_new != new_count:
                raise ValueError(f"hunk count mismatch for {relative}")
        if not saw_hunk:
            # A header-only /dev/null transition represents creation or
            # deletion of an empty file. Other header-only patches are invalid.
            if kind not in {ChangeKind.CREATE, ChangeKind.DELETE} or original:
                raise ValueError(f"file patch has no hunks: {relative}")
        output.extend(original[source_cursor:])
        content = None if kind == ChangeKind.DELETE else "".join(output)
        operations.append(
            PatchHunk(
                path=relative,
                kind=kind,
                content=content,
                expected_sha256=expected.sha256 if expected else None,
            )
        )
    if not operations:
        raise ValueError("patch contains no file operations")
    return operations


def _header_path(label: str) -> str | None:
    if label == "/dev/null":
        return None
    for prefix in ("a/", "b/"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    if not label or Path(label).is_absolute() or ".." in Path(label).parts:
        raise ValueError(f"unsafe patch path: {label}")
    return Path(label).as_posix()


def _scan_file_states(root: Path) -> dict[str, FileState]:
    states: dict[str, FileState] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(root).as_posix()
            if is_excluded_relative_path(relative):
                continue
            data = path.read_bytes()
            states[relative] = FileState(relative, hashlib.sha256(data).hexdigest(), len(data))
    return states


def _encode_no_newline_markers(lines: list[str]) -> str:
    encoded: list[str] = []
    for line in lines:
        if line[:1] in {" ", "+", "-"} and not line.endswith(("\n", "\r")):
            encoded.append(line + "\n")
            encoded.append("\\ No newline at end of file\n")
        else:
            encoded.append(line)
    return "".join(encoded)


def _first_symlink(root: Path) -> str | None:
    for path in root.rglob("*"):
        if path.is_symlink():
            return path.relative_to(root).as_posix()
    return None
