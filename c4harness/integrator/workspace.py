"""Integration workspace lifecycle primitives.

Creates one isolated canonical snapshot for an entire graph execution.  The
snapshot copies ordinary files (skipping symlinks,
``.git``, caches, virtualenvs, and sockets) and preserves empty
directories that are useful for the worker.

Design guarantees
-----------------
* **No symlinks** – every entry is a real file or directory.
* **Git-agnostic** – works for both Git and non-Git directories.
* **Path-safe** – all internal paths are normalized; traversal is rejected.
* **Non-destructive** – the source directory is never mutated.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Sentinel stored in ``IntegrationSnapshot.empty_dirs`` for entries that
# have no files but should be preserved (e.g. ``output/``).
EMPTY_DIR_SENTINEL = object()

# Directories whose *names* (at any level) cause the entry to be skipped.
_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    ".c4harness",
    ".cost-router",  # ignored backup; never used as active runtime data
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".eggs",
})

# Socket-like suffixes that are skipped even if they look like files.
_SOCKET_EXTENSIONS: frozenset[str] = frozenset({".sock", ".socket", ".pipe"})


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

def normalize_repo_relative(path_str: str, repo: Path) -> Path:
    """Normalize *path_str* as a relative path under *repo*.

    The returned path is always relative to *repo* and uses forward slashes.
    Traversal components (``..``) and absolute inputs are rejected with
    :class:`ValueError`.

    Parameters
    ----------
    path_str:
        A string that may be relative to *repo* or absolute.
    repo:
        The repository root (resolved before comparison).

    Returns
    -------
    Path
        A forward-slash relative ``Path`` safe for joining under *repo*.

    Raises
    ------
    ValueError
        If the path escapes the repository boundary.
    """
    p = Path(path_str)
    if p.is_absolute():
        resolved = p.resolve()
        repo_resolved = repo.resolve()
        if resolved == repo_resolved:
            return Path(".")
        if not str(resolved).startswith(str(repo_resolved) + os.sep):
            raise ValueError(f"Absolute path escapes repository: {path_str}")
        return resolved.relative_to(repo_resolved)

    # Relative path: reject explicit traversal.
    parts = p.parts
    if ".." in parts:
        raise ValueError(f"Path contains traversal: {path_str}")
    if not parts:
        return Path(".")

    # Verify the resolved path stays within repo.
    resolved = (repo / p).resolve()
    repo_resolved = repo.resolve()
    if resolved == repo_resolved:
        return Path(".")
    if not str(resolved).startswith(str(repo_resolved) + os.sep):
        raise ValueError(f"Path escapes repository after resolution: {path_str}")
    return resolved.relative_to(repo_resolved)


# ---------------------------------------------------------------------------
# File state
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FileState:
    """SHA-256 fingerprint of a single ordinary file."""

    path: str          # repo-relative, forward-slash
    sha256: str        # hex digest
    size: int          # bytes

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class IntegrationSnapshot:
    """Immutable-ish container for an isolated integration workspace.

    Attributes
    ----------
    root:
        Absolute path of the snapshot directory on disk.
    graph_id:
        Identifier of the graph execution that owns this snapshot.
    source_repo:
        Absolute path of the source repository that was copied.
    file_states:
        Mapping from repo-relative path to :class:`FileState`.
    empty_dirs:
        Set of repo-relative directory paths that are empty in the source
        but should be preserved for the worker.
    """

    root: Path
    graph_id: str
    node_id: str | None
    source_repo: Path
    file_states: dict[str, FileState] = field(default_factory=dict)
    source_baseline: dict[str, FileState] = field(default_factory=dict)
    empty_dirs: set[str] = field(default_factory=set)
    pending_rollback: Path | None = field(default=None, repr=False)

    def relative_paths(self) -> set[str]:
        """Return the set of all repo-relative paths in this snapshot."""
        return set(self.file_states.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "source_repo": str(self.source_repo),
            "file_count": len(self.file_states),
            "empty_dir_count": len(self.empty_dirs),
        }


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class IntegrationResult:
    """Outcome of creating an integration snapshot."""

    snapshot: IntegrationSnapshot | None
    copied_files: int
    skipped_entries: int
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.snapshot is not None and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "copied_files": self.copied_files,
            "skipped_entries": self.skipped_entries,
            "error_count": len(self.errors),
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
        }


# ---------------------------------------------------------------------------
# Snapshot creation
# ---------------------------------------------------------------------------

def create_integration_snapshot(
    source: Path,
    *,
    graph_id: str,
    node_id: str | None = None,
    parent_dir: Path | None = None,
) -> IntegrationResult:
    """Create one isolated canonical copy of *source* for a graph execution.

    Parameters
    ----------
    source:
        The directory to copy.  Must exist and be a directory.
    graph_id:
        A stable identifier for the owning graph execution.
    node_id:
        Deprecated optional metadata kept for compatibility.  It does not
        create a per-node directory; all nodes in a graph share one snapshot.
    parent_dir:
        Where to create the snapshot directory.  Defaults to a temporary
        directory under the system temp root.

    Returns
    -------
    IntegrationResult
        Contains the snapshot (on success) and bookkeeping counts.
    """
    source = source.resolve()
    if not source.is_dir():
        return IntegrationResult(
            snapshot=None,
            copied_files=0,
            skipped_entries=0,
            errors=[f"Source is not a directory: {source}"],
        )

    graph_path = Path(graph_id)
    if (
        not graph_id
        or graph_id in {".", ".."}
        or graph_path.is_absolute()
        or len(graph_path.parts) != 1
    ):
        raise ValueError(f"Unsafe graph_id: {graph_id!r}")

    # Build one canonical root per graph: <parent_dir>/<graph_id>/workspace.
    if parent_dir is None:
        import tempfile
        parent_dir = Path(tempfile.mkdtemp(prefix="integration_"))
    else:
        parent_dir = parent_dir.resolve()
    snapshot_root = parent_dir / graph_id / "workspace"
    if snapshot_root.exists():
        raise FileExistsError(f"Integration workspace already exists: {snapshot_root}")
    snapshot_root.mkdir(parents=True, exist_ok=True)

    file_states: dict[str, FileState] = {}
    empty_dirs: set[str] = set()
    copied = 0
    skipped = 0
    errors: list[str] = []

    for entry in sorted(_walk_source(source)):
        relative = entry.relative_to(source)
        relative_str = relative.as_posix()

        # Skip excluded directory trees.
        if _is_excluded(entry, source):
            skipped += 1
            continue

        # Skip symlinks.
        try:
            if entry.is_symlink():
                skipped += 1
                continue
        except OSError:
            skipped += 1
            continue

        # Skip sockets and other special files.
        if entry.is_file() and _is_socket(entry):
            skipped += 1
            continue

        if entry.is_dir():
            # Record empty directories.
            if _is_empty_dir(entry):
                empty_dirs.add(relative_str)
                dest = snapshot_root / relative
                dest.mkdir(parents=True, exist_ok=True)
            continue

        if entry.is_file():
            try:
                data = entry.read_bytes()
            except OSError as exc:
                errors.append(f"Cannot read {relative_str}: {exc}")
                skipped += 1
                continue

            sha = hashlib.sha256(data).hexdigest()
            dest = snapshot_root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_bytes(data)
            except OSError as exc:
                errors.append(f"Cannot write {relative_str}: {exc}")
                skipped += 1
                continue

            file_states[relative_str] = FileState(
                path=relative_str,
                sha256=sha,
                size=len(data),
            )
            copied += 1
        else:
            # Sockets, FIFOs, device files, etc.
            skipped += 1

    snapshot = IntegrationSnapshot(
        root=snapshot_root,
        graph_id=graph_id,
        node_id=node_id,
        source_repo=source,
        file_states=file_states,
        source_baseline=dict(file_states),
        empty_dirs=empty_dirs,
    )
    return IntegrationResult(
        snapshot=snapshot,
        copied_files=copied,
        skipped_entries=skipped,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk_source(source: Path) -> list[Path]:
    """Return all entries under *source* sorted for determinism.

    Uses ``os.walk`` instead of ``Path.rglob`` to have explicit control
    over symlink following (we don't follow).  Prunes excluded directories
    in-place to avoid descending into them.
    """
    entries: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        # Prune excluded directories in-place so os.walk won't descend.
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _EXCLUDED_DIR_NAMES and not d.endswith(".egg-info")
        )
        filenames.sort()
        for name in dirnames:
            entries.append(Path(dirpath) / name)
        for name in filenames:
            entries.append(Path(dirpath) / name)
    return entries


def _is_excluded(entry: Path, source: Path) -> bool:
    """Return ``True`` if *entry* or any ancestor is an excluded directory."""
    try:
        relative = entry.relative_to(source)
    except ValueError:
        return True
    return is_excluded_relative_path(relative)


def is_excluded_relative_path(relative: Path | str) -> bool:
    """Return whether a source-relative path is excluded from snapshots."""
    parts = Path(relative).parts
    for part in parts:
        if part in _EXCLUDED_DIR_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
    return False


def _is_socket(entry: Path) -> bool:
    """Return ``True`` if *entry* looks like a socket or pipe."""
    suffix = entry.suffix.lower()
    if suffix in _SOCKET_EXTENSIONS:
        return True
    try:
        mode = entry.stat().st_mode
        return (mode & 0o170000) == 0o140000  # S_IFSOCK
    except OSError:
        return False


def _is_empty_dir(entry: Path) -> bool:
    """Return ``True`` if *entry* is a directory with no children."""
    try:
        return entry.is_dir() and not any(entry.iterdir())
    except OSError:
        return False
