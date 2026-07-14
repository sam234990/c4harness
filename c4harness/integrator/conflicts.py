"""Write-set reservation and optimistic conflict detection.

Provides node-scoped write-set reservations without TTL.  Overlapping
active write paths must conflict, and release is deterministic.

Design guarantees
-----------------
* **No TTL** – reservations persist until explicitly released.
* **Deterministic release** – a node releases exactly the paths it reserved.
* **Overlap detection** – two active reservations on the same path conflict.
* **Optimistic conflict detection** – compares a snapshot baseline against
  the current source state to detect external modifications.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from .workspace import IntegrationSnapshot, is_excluded_relative_path


# ---------------------------------------------------------------------------
# Conflict types
# ---------------------------------------------------------------------------

class ConflictKind(str, Enum):
    FILE_MODIFIED = "file_modified"     # source file changed since baseline
    FILE_CREATED = "file_created"       # new file appeared in source
    FILE_DELETED = "file_deleted"       # source file was removed
    WRITE_CONFLICT = "write_conflict"   # overlapping active reservations


@dataclass(frozen=True, slots=True)
class Conflict:
    """A single conflict between the snapshot baseline and source state."""

    path: str               # repo-relative
    kind: ConflictKind
    baseline_sha256: str | None
    source_sha256: str | None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "baseline_sha256": self.baseline_sha256,
            "source_sha256": self.source_sha256,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Reservation records
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ReservationRecord:
    """A single write-set reservation."""

    node_id: str
    path: str           # repo-relative, forward-slash
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "path": self.path,
            "released": self.released,
        }


# ---------------------------------------------------------------------------
# Write reservation manager
# ---------------------------------------------------------------------------

class WriteReservationManager:
    """Node-scoped write-set reservations without TTL.

    Usage::

        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py", "lib/utils.py"])
        mgr.reserve("node-2", ["src/main.py"])  # raises ValueError
        mgr.release_node("node-1")
    """

    def __init__(self) -> None:
        # path -> active ReservationRecord
        self._active: dict[str, ReservationRecord] = {}
        # all records (including released) for audit
        self._all: list[ReservationRecord] = []
        self._lock = threading.RLock()

    @property
    def active_reservations(self) -> dict[str, ReservationRecord]:
        """Currently active (unreleased) reservations keyed by path."""
        with self._lock:
            return dict(self._active)

    @property
    def all_records(self) -> list[ReservationRecord]:
        """All reservation records including released ones."""
        with self._lock:
            return list(self._all)

    def reserve(self, node_id: str, paths: list[str]) -> list[ReservationRecord]:
        """Reserve *paths* for *node_id*.

        Overlapping active reservations from **other** nodes cause a
        :class:`ValueError` and no paths are reserved (all-or-nothing).

        Parameters
        ----------
        node_id:
            Identifier of the graph node requesting the reservation.
        paths:
            Repo-relative paths to reserve.

        Returns
        -------
        list[ReservationRecord]
            The newly created reservation records.

        Raises
        ------
        ValueError
            If any path is already actively reserved by another node.
        """
        with self._lock:
            # Check and acquire under one lock so concurrent threads cannot
            # both pass preflight for overlapping paths.
            normalized = [_canonical_write_path(path) for path in paths]
            conflicts: list[str] = []
            for path in normalized:
                for existing_path, existing in self._active.items():
                    if existing.node_id != node_id and _paths_overlap(path, existing_path):
                        conflicts.append(
                            f"{path}: overlaps {existing_path} reserved by {existing.node_id}"
                        )
            if conflicts:
                raise ValueError("Write reservation conflict: " + "; ".join(conflicts))

            records: list[ReservationRecord] = []
            for path in normalized:
                existing = self._active.get(path)
                if existing is not None and existing.node_id == node_id:
                    continue
                record = ReservationRecord(node_id=node_id, path=path)
                self._active[path] = record
                self._all.append(record)
                records.append(record)
            return records

    def release(self, node_id: str, path: str) -> bool:
        """Release a single reservation.

        Returns ``True`` if the reservation existed and was released,
        ``False`` if no active reservation was found for this node/path.
        """
        normalized = _canonical_write_path(path)
        with self._lock:
            existing = self._active.get(normalized)
            if existing is None or existing.node_id != node_id:
                return False
            released = ReservationRecord(
                node_id=node_id, path=normalized, released=True,
            )
            del self._active[normalized]
            self._all.append(released)
            return True

    def release_node(self, node_id: str) -> int:
        """Release all active reservations for *node_id*.

        Returns the number of released reservations.
        """
        with self._lock:
            to_release = [
                path
                for path, rec in self._active.items()
                if rec.node_id == node_id
            ]
            for path in to_release:
                self.release(node_id, path)
            return len(to_release)

    def is_reserved(self, path: str) -> ReservationRecord | None:
        """Return the active reservation for *path*, or ``None``."""
        normalized = _canonical_write_path(path)
        with self._lock:
            matches = [
                record
                for active_path, record in self._active.items()
                if _paths_overlap(normalized, active_path)
            ]
            return sorted(matches, key=lambda item: item.path)[0] if matches else None

    def node_paths(self, node_id: str) -> set[str]:
        """Return the set of paths currently reserved by *node_id*."""
        with self._lock:
            return {
                path
                for path, rec in self._active.items()
                if rec.node_id == node_id
            }


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts(
    snapshot: IntegrationSnapshot,
    reservation_manager: WriteReservationManager | None = None,
    paths: set[str] | None = None,
) -> list[Conflict]:
    """Compare the snapshot baseline against the current source state.

    Parameters
    ----------
    snapshot:
        An integration snapshot whose ``file_states`` represent the
        baseline captured at snapshot creation time.
    reservation_manager:
        If provided, any paths with overlapping active reservations are
        reported as ``WRITE_CONFLICT`` conflicts.

    Returns
    -------
    list[Conflict]
        All detected conflicts.  An empty list means the source has not
        diverged from the baseline.
    """
    source = snapshot.source_repo
    baseline = snapshot.source_baseline
    conflicts: list[Conflict] = []
    selected = {_canonical_write_path(path) for path in paths} if paths else None

    def relevant(path: str) -> bool:
        return selected is None or any(_paths_overlap(path, item) for item in selected)

    # Check files in baseline against current source.
    for relative_str, base_state in baseline.items():
        if not relevant(relative_str):
            continue
        source_file = source / relative_str
        if not source_file.exists():
            conflicts.append(Conflict(
                path=relative_str,
                kind=ConflictKind.FILE_DELETED,
                baseline_sha256=base_state.sha256,
                source_sha256=None,
                detail="File was deleted from source since snapshot",
            ))
            continue
        if source_file.is_symlink():
            conflicts.append(Conflict(
                path=relative_str,
                kind=ConflictKind.FILE_MODIFIED,
                baseline_sha256=base_state.sha256,
                source_sha256=None,
                detail="Baseline file became a symlink in source",
            ))
            continue
        if not source_file.is_file():
            conflicts.append(Conflict(
                path=relative_str,
                kind=ConflictKind.FILE_MODIFIED,
                baseline_sha256=base_state.sha256,
                source_sha256=None,
                detail="Baseline file is no longer a regular source file",
            ))
            continue
        try:
            current_data = source_file.read_bytes()
        except OSError as exc:
            conflicts.append(Conflict(
                path=relative_str,
                kind=ConflictKind.FILE_MODIFIED,
                baseline_sha256=base_state.sha256,
                source_sha256=None,
                detail=f"Baseline file cannot be read from source: {exc}",
            ))
            continue
        current_sha = hashlib.sha256(current_data).hexdigest()
        if current_sha != base_state.sha256:
            conflicts.append(Conflict(
                path=relative_str,
                kind=ConflictKind.FILE_MODIFIED,
                baseline_sha256=base_state.sha256,
                source_sha256=current_sha,
                detail="File was modified in source since snapshot",
            ))

    # Check for new files in source that aren't in baseline.
    # (Only scan non-excluded ordinary files.)
    try:
        for entry in source.rglob("*"):
            relative = entry.relative_to(source).as_posix()
            if is_excluded_relative_path(relative):
                continue
            if entry.is_symlink():
                if relative not in baseline and relevant(relative):
                    conflicts.append(Conflict(
                        path=relative,
                        kind=ConflictKind.FILE_CREATED,
                        baseline_sha256=None,
                        source_sha256=None,
                        detail="New symlink appeared in source since snapshot",
                    ))
                continue
            if not entry.is_file():
                # Directories are scopes rather than patchable file targets;
                # special non-directory entries fail closed when relevant.
                if not entry.is_dir() and relative not in baseline and relevant(relative):
                    conflicts.append(Conflict(
                        path=relative,
                        kind=ConflictKind.FILE_CREATED,
                        baseline_sha256=None,
                        source_sha256=None,
                        detail="New non-regular entry appeared in source since snapshot",
                    ))
                continue
            if relative not in baseline and relevant(relative):
                try:
                    data = entry.read_bytes()
                except OSError:
                    continue
                conflicts.append(Conflict(
                    path=relative,
                    kind=ConflictKind.FILE_CREATED,
                    baseline_sha256=None,
                    source_sha256=hashlib.sha256(data).hexdigest(),
                    detail="New file appeared in source since snapshot",
                ))
    except OSError:
        pass

    # Check for overlapping write reservations between different nodes.
    if reservation_manager is not None:
        active = reservation_manager.active_reservations
        items = list(active.items())
        reported: set[tuple[str, str]] = set()
        for i in range(len(items)):
            path_a, rec_a = items[i]
            for j in range(i + 1, len(items)):
                path_b, rec_b = items[j]
                if rec_a.node_id == rec_b.node_id:
                    continue
                # Check if paths overlap (one is prefix of the other).
                if (
                    path_a == path_b
                    or path_a.startswith(path_b + "/")
                    or path_b.startswith(path_a + "/")
                ):
                    pair = tuple(sorted([rec_a.node_id, rec_b.node_id]))
                    if pair in reported:
                        continue
                    reported.add(pair)
                    conflicts.append(Conflict(
                        path=path_a,
                        kind=ConflictKind.WRITE_CONFLICT,
                        baseline_sha256=None,
                        source_sha256=None,
                        detail=(
                            f"Overlapping reservation: {rec_a.node_id} "
                            f"({path_a}) and {rec_b.node_id} ({path_b})"
                        ),
                    ))

    return conflicts


def _canonical_write_path(path: str) -> str:
    """Return a safe lexical repo-relative path for reservation comparisons."""
    normalized = path.replace("\\", "/").strip("/")
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Invalid write path: {path}")
    return candidate.as_posix()


def _paths_overlap(left: str, right: str) -> bool:
    """Component-aware equality/ancestor overlap (``src`` != ``src2``)."""
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shorter = min(len(left_parts), len(right_parts))
    return left_parts[:shorter] == right_parts[:shorter]
