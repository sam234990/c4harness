"""Graph-scoped integration session used by the application orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading

from .conflicts import Conflict, WriteReservationManager, detect_conflicts
from .patches import PatchApplier, PatchResult, _first_symlink, _scan_file_states
from .workspace import IntegrationSnapshot, create_integration_snapshot


@dataclass(slots=True)
class IntegrationAttempt:
    patch_result: PatchResult | None = None
    conflicts: list[Conflict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    expected_states: dict[str, object] = field(default_factory=dict, repr=False)
    _lock_held: bool = field(default=False, repr=False)

    @property
    def accepted(self) -> bool:
        return (
            not self.conflicts
            and not self.issues
            and self.patch_result is not None
            and self.patch_result.success
        )


class GraphIntegrationSession:
    """Own one canonical, isolated workspace for an entire task graph."""

    def __init__(self, snapshot: IntegrationSnapshot) -> None:
        self.snapshot = snapshot
        self.reservations = WriteReservationManager()
        # Worker subprocesses may run concurrently, but the integration
        # workspace is one canonical directory.  Applying, verifying, and
        # committing a patch therefore forms a short serialized transaction.
        # This still permits expensive worker execution to overlap while
        # avoiding whole-workspace swap races in PatchApplier.
        self._integration_lock = threading.RLock()

    @classmethod
    def create(
        cls,
        source_repo: Path,
        *,
        graph_id: str,
        parent_dir: Path,
    ) -> "GraphIntegrationSession":
        result = create_integration_snapshot(
            source_repo,
            graph_id=graph_id,
            parent_dir=parent_dir,
        )
        if not result.success or result.snapshot is None:
            detail = "; ".join(result.errors) or "unknown snapshot error"
            raise RuntimeError(f"Cannot create integration workspace: {detail}")
        return cls(result.snapshot)

    @property
    def root(self) -> Path:
        return self.snapshot.root

    def relative_path(self, path: Path) -> str:
        """Translate a source/workspace path to a source-relative label."""
        candidate = path if path.is_absolute() else self.snapshot.source_repo / path
        resolved = candidate.resolve()
        for root in (self.snapshot.source_repo.resolve(), self.root.resolve()):
            try:
                return resolved.relative_to(root).as_posix()
            except ValueError:
                continue
        raise ValueError(f"Path is outside the graph repository: {path}")

    def workspace_path(self, path: Path) -> Path:
        return self.root / self.relative_path(path)

    def reserve(self, node_id: str, write_paths: tuple[Path, ...]) -> None:
        self.reservations.reserve(
            node_id,
            [self.relative_path(path) for path in write_paths],
        )

    def release(self, node_id: str) -> None:
        self.reservations.release_node(node_id)

    def apply_proposal(
        self,
        *,
        patch_path: Path,
        write_paths: tuple[Path, ...],
    ) -> IntegrationAttempt:
        self._integration_lock.acquire()
        keep_lock = False
        try:
            allowed = {self.relative_path(path) for path in write_paths}
            conflicts = detect_conflicts(self.snapshot, paths=allowed)
            if conflicts:
                return IntegrationAttempt(conflicts=conflicts)
            applier = PatchApplier(self.snapshot, allowed_paths=allowed)
            patch_result = applier.apply_unified_diff(
                patch_path,
                retain_rollback=True,
            )
            issues = [*patch_result.failed, *patch_result.violations]
            # A successful retained transaction is completed by commit() or
            # rollback() in the same graph-node thread.
            keep_lock = patch_result.success and patch_result.rollback_dir is not None
            return IntegrationAttempt(
                patch_result=patch_result,
                issues=issues,
                expected_states=dict(self.snapshot.file_states),
                _lock_held=keep_lock,
            )
        finally:
            if not keep_lock:
                self._integration_lock.release()

    def commit(self, attempt: IntegrationAttempt) -> None:
        try:
            if attempt.patch_result is not None:
                PatchApplier(self.snapshot).commit(attempt.patch_result)
        finally:
            self._release_attempt_lock(attempt)

    def post_verification_issues(self, attempt: IntegrationAttempt) -> list[str]:
        """Detect verifier side effects before a retained patch is committed."""
        symlink = _first_symlink(self.root)
        if symlink is not None:
            return [f"Post verifier created a symlink: {symlink}"]
        try:
            current = _scan_file_states(self.root)
        except OSError as exc:
            return [f"Cannot rescan integration workspace after verification: {exc}"]
        expected = attempt.expected_states
        changed = sorted(
            path
            for path in set(expected) | set(current)
            if expected.get(path) != current.get(path)
        )
        if changed:
            return [
                "Post verifier changed files outside the patch transaction: "
                + ", ".join(changed)
            ]
        return []

    def rollback(self, attempt: IntegrationAttempt) -> bool:
        try:
            if attempt.patch_result is None:
                return False
            return PatchApplier(self.snapshot).rollback(attempt.patch_result)
        finally:
            self._release_attempt_lock(attempt)

    def _release_attempt_lock(self, attempt: IntegrationAttempt) -> None:
        if attempt._lock_held:
            attempt._lock_held = False
            self._integration_lock.release()
