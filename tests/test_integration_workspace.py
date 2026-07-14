"""Comprehensive stdlib-only tests for graph-scoped integration workspaces.

Covers:
- Directory with no .git (non-Git repo)
- Dirty-looking files (weird names, binary-like content, special chars)
- Create / modify / delete text files via patches
- Traversal rejection (path normalization)
- Stale baseline conflict detection
- Overlapping write-set reservations
- Proof that source files remain unchanged after all operations
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from c4harness.integrator import (
    ChangeKind,
    Conflict,
    ConflictKind,
    FileState,
    IntegrationResult,
    IntegrationSnapshot,
    GraphIntegrationSession,
    PatchApplier,
    PatchHunk,
    PatchResult,
    WriteReservationManager,
    create_integration_snapshot,
    detect_conflicts,
    generate_unified_diff,
    normalize_repo_relative,
)


class NormalizeRepoRelativeTests(unittest.TestCase):
    """Tests for safe path normalization."""

    def test_relative_simple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = normalize_repo_relative("src/main.py", repo)
            self.assertEqual(result, Path("src/main.py"))

    def test_relative_nested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = normalize_repo_relative("a/b/c/d.txt", repo)
            self.assertEqual(result, Path("a/b/c/d.txt"))

    def test_dot_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = normalize_repo_relative(".", repo)
            self.assertEqual(result, Path("."))

    def test_absolute_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            result = normalize_repo_relative(str(repo / "src" / "main.py"), repo)
            self.assertEqual(result, Path("src/main.py"))

    def test_absolute_equals_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = normalize_repo_relative(str(repo), repo)
            self.assertEqual(result, Path("."))

    def test_rejects_dotdot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                normalize_repo_relative("../etc/passwd", repo)

    def test_rejects_dotdot_in_middle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                normalize_repo_relative("src/../../../etc/passwd", repo)

    def test_rejects_absolute_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                normalize_repo_relative("/etc/passwd", repo)

    def test_rejects_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            with self.assertRaises(ValueError):
                normalize_repo_relative(str(Path(tmp) / "other" / "file"), repo)


class CreateSnapshotNoGitTests(unittest.TestCase):
    """Snapshot creation for a directory without .git."""

    def test_copies_ordinary_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / "main.py").write_text("print('hello')")
            (source / "lib").mkdir()
            (source / "lib" / "utils.py").write_text("x = 1")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            self.assertTrue(result.success)
            self.assertEqual(result.copied_files, 2)
            self.assertIsNotNone(result.snapshot)

            snap = result.snapshot
            self.assertIn("main.py", snap.file_states)
            self.assertIn("lib/utils.py", snap.file_states)

            # Verify content was copied.
            copied_main = snap.root / "main.py"
            self.assertEqual(copied_main.read_text(), "print('hello')")

    def test_sha256_matches_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            content = "some deterministic content\n"
            (source / "data.txt").write_text(content)

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            expected_sha = hashlib.sha256(content.encode()).hexdigest()
            self.assertEqual(snap.file_states["data.txt"].sha256, expected_sha)

    def test_excludes_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            pycache = source / "__pycache__"
            pycache.mkdir()
            (pycache / "module.cpython-312.pyc").write_bytes(b"\x00\x01")
            (source / "module.py").write_text("# source")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("module.py", snap.file_states)
            # __pycache__ should not appear.
            for path in snap.file_states:
                self.assertNotIn("__pycache__", path)

    def test_excludes_dot_c4harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            cr = source / ".c4harness"
            cr.mkdir()
            (cr / "data.json").write_text("{}")
            (source / "README.md").write_text("# Project")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("README.md", snap.file_states)
            for path in snap.file_states:
                self.assertNotIn(".c4harness", path)

    def test_excludes_git_directory(self) -> None:
        """Even without being a Git repo, .git dirs are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            git_dir = source / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
            (source / "file.txt").write_text("content")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("file.txt", snap.file_states)
            for path in snap.file_states:
                self.assertNotIn(".git", path)

    def test_excludes_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / "real.txt").write_text("real content")
            try:
                os.symlink(
                    source / "real.txt",
                    source / "link.txt",
                )
            except OSError:
                self.skipTest("Cannot create symlinks in this environment")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("real.txt", snap.file_states)
            self.assertNotIn("link.txt", snap.file_states)

    def test_preserves_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / "output").mkdir()
            (source / "main.py").write_text("pass")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("output", snap.empty_dirs)
            self.assertTrue((snap.root / "output").is_dir())

    def test_rejects_unsafe_graph_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            with self.assertRaises(ValueError):
                create_integration_snapshot(
                    source,
                    graph_id="../escaped",
                    parent_dir=Path(tmp) / "out",
                )


class DirtyFileTests(unittest.TestCase):
    """Tests for files with unusual names or content."""

    def test_files_with_spaces_in_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / "my file.txt").write_text("spaced")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("my file.txt", snap.file_states)
            self.assertEqual(
                (snap.root / "my file.txt").read_text(), "spaced"
            )

    def test_files_with_unicode_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            content = "你好世界 🌍\n"
            (source / "unicode.txt").write_text(content, encoding="utf-8")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("unicode.txt", snap.file_states)
            self.assertEqual(
                (snap.root / "unicode.txt").read_text(encoding="utf-8"),
                content,
            )

    def test_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / "empty.txt").write_text("")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn("empty.txt", snap.file_states)
            self.assertEqual(snap.file_states["empty.txt"].size, 0)

    def test_large_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            content = "x" * 100_000
            (source / "large.txt").write_text(content)

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertEqual(snap.file_states["large.txt"].size, 100_000)

    def test_file_with_dot_prefix_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            (source / ".env").write_text("SECRET=123")
            (source / ".gitignore").write_text("*.pyc")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "out",
            )
            snap = result.snapshot
            self.assertIn(".env", snap.file_states)
            self.assertIn(".gitignore", snap.file_states)


class PatchCreateModifyDeleteTests(unittest.TestCase):
    """Tests for create, modify, and delete via PatchApplier."""

    def _make_snapshot(
        self, tmp: str, files: dict[str, str] | None = None,
    ) -> tuple[Path, IntegrationSnapshot]:
        source = Path(tmp) / "source"
        source.mkdir()
        for name, content in (files or {}).items():
            p = source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        result = create_integration_snapshot(
            source, graph_id="g-test", node_id="n-test",
            parent_dir=Path(tmp) / "snapshots",
        )
        return source, result.snapshot

    def test_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, snap = self._make_snapshot(tmp)
            applier = PatchApplier(snap, allowed_paths={"new.txt"})
            hunks = [PatchHunk(
                path="new.txt",
                kind=ChangeKind.CREATE,
                content="new content",
            )]
            result = applier.apply(hunks)
            self.assertTrue(result.success)
            self.assertEqual(len(result.applied), 1)
            self.assertEqual(result.applied[0].kind, ChangeKind.CREATE)
            # Verify file was created in snapshot.
            self.assertEqual(
                (snap.root / "new.txt").read_text(), "new content"
            )
            # Verify SHA-256 was recorded.
            self.assertIn("new.txt", snap.file_states)

    def test_missing_file_allowlist_is_exact_not_directory_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp)
            result = PatchApplier(snap, allowed_paths={"new.py"}).apply([
                PatchHunk("new.py/child", ChangeKind.CREATE, "bad")
            ])
            self.assertFalse(result.success)
            self.assertTrue(result.violations)

    def test_unified_diff_preserves_missing_final_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"plain.txt": "old"})
            patch = Path(tmp) / "change.patch"
            patch.write_text(generate_unified_diff("plain.txt", "old", "new"))
            result = PatchApplier(snap, {"plain.txt"}).apply_unified_diff(patch)
            self.assertTrue(result.success, result.to_dict())
            self.assertEqual((snap.root / "plain.txt").read_bytes(), b"new")

    def test_unified_diff_supports_empty_file_create_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"remove.txt": ""})
            create_patch = Path(tmp) / "create.patch"
            create_patch.write_text(
                generate_unified_diff(
                    "empty.txt", "", "", existed_before=False, exists_after=True
                )
            )
            created = PatchApplier(snap, {"empty.txt"}).apply_unified_diff(create_patch)
            self.assertTrue(created.success, created.to_dict())
            self.assertEqual((snap.root / "empty.txt").read_bytes(), b"")

            delete_patch = Path(tmp) / "delete.patch"
            delete_patch.write_text(
                generate_unified_diff(
                    "remove.txt", "", "", existed_before=True, exists_after=False
                )
            )
            deleted = PatchApplier(snap, {"remove.txt"}).apply_unified_diff(delete_patch)
            self.assertTrue(deleted.success, deleted.to_dict())
            self.assertFalse((snap.root / "remove.txt").exists())

    def test_retained_transaction_must_be_resolved_before_next_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"state.txt": "one\n"})
            first = PatchApplier(snap, {"state.txt"}).apply(
                [PatchHunk("state.txt", ChangeKind.MODIFY, "two\n")],
                retain_rollback=True,
            )
            self.assertTrue(first.success)
            second = PatchApplier(snap, {"state.txt"}).apply(
                [PatchHunk("state.txt", ChangeKind.MODIFY, "three\n")]
            )
            self.assertFalse(second.success)
            self.assertTrue(PatchApplier(snap).rollback(first))
            self.assertEqual((snap.root / "state.txt").read_text(), "one\n")

    def test_modify_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, snap = self._make_snapshot(
                tmp, {"config.yaml": "key: old"}
            )
            old_sha = snap.file_states["config.yaml"].sha256
            applier = PatchApplier(snap, allowed_paths={"config.yaml"})
            hunks = [PatchHunk(
                path="config.yaml",
                kind=ChangeKind.MODIFY,
                content="key: new",
                expected_sha256=old_sha,
            )]
            result = applier.apply(hunks)
            self.assertTrue(result.success)
            self.assertEqual(
                (snap.root / "config.yaml").read_text(), "key: new"
            )
            new_sha = snap.file_states["config.yaml"].sha256
            self.assertNotEqual(old_sha, new_sha)

    def test_delete_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, snap = self._make_snapshot(
                tmp, {"obsolete.txt": "delete me"}
            )
            old_sha = snap.file_states["obsolete.txt"].sha256
            applier = PatchApplier(snap, allowed_paths={"obsolete.txt"})
            hunks = [PatchHunk(
                path="obsolete.txt",
                kind=ChangeKind.DELETE,
                expected_sha256=old_sha,
            )]
            result = applier.apply(hunks)
            self.assertTrue(result.success)
            self.assertFalse((snap.root / "obsolete.txt").exists())
            self.assertNotIn("obsolete.txt", snap.file_states)

    def test_create_modify_delete_in_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, snap = self._make_snapshot(
                tmp, {"existing.txt": "old content"}
            )
            old_sha = snap.file_states["existing.txt"].sha256
            applier = PatchApplier(snap, allowed_paths={
                "new.txt", "existing.txt", "remove.txt",
            })
            # First create a file to delete.
            (snap.root / "remove.txt").write_text("temp")
            snap.file_states["remove.txt"] = FileState(
                path="remove.txt",
                sha256=hashlib.sha256(b"temp").hexdigest(),
                size=4,
            )
            remove_sha = snap.file_states["remove.txt"].sha256

            hunks = [
                PatchHunk(
                    path="new.txt",
                    kind=ChangeKind.CREATE,
                    content="brand new",
                ),
                PatchHunk(
                    path="existing.txt",
                    kind=ChangeKind.MODIFY,
                    content="updated content",
                    expected_sha256=old_sha,
                ),
                PatchHunk(
                    path="remove.txt",
                    kind=ChangeKind.DELETE,
                    expected_sha256=remove_sha,
                ),
            ]
            result = applier.apply(hunks)
            self.assertTrue(result.success)
            self.assertEqual(len(result.applied), 3)
            self.assertEqual(
                (snap.root / "new.txt").read_text(), "brand new"
            )
            self.assertEqual(
                (snap.root / "existing.txt").read_text(), "updated content"
            )
            self.assertFalse((snap.root / "remove.txt").exists())

    def test_create_requires_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp)
            applier = PatchApplier(snap, allowed_paths={"f.txt"})
            hunks = [PatchHunk(
                path="f.txt",
                kind=ChangeKind.CREATE,
                content=None,
            )]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            self.assertTrue(result.failed)

    def test_modify_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp)
            applier = PatchApplier(snap, allowed_paths={"ghost.txt"})
            hunks = [PatchHunk(
                path="ghost.txt",
                kind=ChangeKind.MODIFY,
                content="nope",
            )]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            self.assertTrue(result.failed)

    def test_delete_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp)
            applier = PatchApplier(snap, allowed_paths={"ghost.txt"})
            hunks = [PatchHunk(
                path="ghost.txt",
                kind=ChangeKind.DELETE,
            )]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            self.assertTrue(result.failed)

    def test_sha_mismatch_on_modify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"f.txt": "content"})
            applier = PatchApplier(snap, allowed_paths={"f.txt"})
            hunks = [PatchHunk(
                path="f.txt",
                kind=ChangeKind.MODIFY,
                content="new",
                expected_sha256="0" * 64,  # wrong SHA
            )]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            self.assertTrue(result.failed)

    def test_sha_mismatch_on_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"f.txt": "content"})
            applier = PatchApplier(snap, allowed_paths={"f.txt"})
            hunks = [PatchHunk(
                path="f.txt",
                kind=ChangeKind.DELETE,
                expected_sha256="0" * 64,
            )]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            self.assertTrue(result.failed)

    def test_atomic_rollback_on_failure(self) -> None:
        """If one hunk fails, none are applied."""
        with tempfile.TemporaryDirectory() as tmp:
            _, snap = self._make_snapshot(tmp, {"ok.txt": "original"})
            ok_sha = snap.file_states["ok.txt"].sha256
            applier = PatchApplier(snap, allowed_paths={"ok.txt", "bad.txt"})
            hunks = [
                PatchHunk(
                    path="ok.txt",
                    kind=ChangeKind.MODIFY,
                    content="changed",
                    expected_sha256=ok_sha,
                ),
                PatchHunk(
                    path="bad.txt",
                    kind=ChangeKind.MODIFY,
                    content="nope",
                    # bad.txt doesn't exist → will fail validation
                ),
            ]
            result = applier.apply(hunks)
            self.assertFalse(result.success)
            # ok.txt should be unchanged (atomic rollback).
            self.assertEqual(
                (snap.root / "ok.txt").read_text(), "original"
            )


class AllowlistEnforcementTests(unittest.TestCase):
    """Tests for path allowlist enforcement in PatchApplier."""

    def test_rejects_path_outside_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "f.txt").write_text("hi")
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap, allowed_paths={"other.txt"})
            hunks = [PatchHunk(
                path="f.txt",
                kind=ChangeKind.MODIFY,
                content="changed",
            )]
            patch_result = applier.apply(hunks)
            self.assertFalse(patch_result.success)
            self.assertTrue(patch_result.violations)

    def test_allows_directory_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap, allowed_paths={"src/"})
            hunks = [PatchHunk(
                path="src/main.py",
                kind=ChangeKind.CREATE,
                content="print('hi')",
            )]
            patch_result = applier.apply(hunks)
            self.assertTrue(patch_result.success)

    def test_rejects_traversal_in_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap, allowed_paths={"../escape"})
            hunks = [PatchHunk(
                path="../escape/evil.txt",
                kind=ChangeKind.CREATE,
                content="pwned",
            )]
            patch_result = applier.apply(hunks)
            self.assertFalse(patch_result.success)

    def test_no_allowlist_allows_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap, allowed_paths=None)
            hunks = [PatchHunk(
                path="anywhere.txt",
                kind=ChangeKind.CREATE,
                content="allowed",
            )]
            patch_result = applier.apply(hunks)
            self.assertTrue(patch_result.success)


class TraversalRejectionTests(unittest.TestCase):
    """Tests that traversal paths are rejected everywhere."""

    def test_normalize_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                normalize_repo_relative("..", repo)

    def test_normalize_rejects_complex_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                normalize_repo_relative("foo/../../bar", repo)

    def test_patch_rejects_traversal_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap)
            hunks = [PatchHunk(
                path="../../../etc/passwd",
                kind=ChangeKind.CREATE,
                content="evil",
            )]
            patch_result = applier.apply(hunks)
            self.assertFalse(patch_result.success)
            # File should not exist outside snapshot.
            evil = Path(tmp) / "etc" / "passwd"
            self.assertFalse(evil.exists())


class StaleBaselineConflictTests(unittest.TestCase):
    """Tests for optimistic conflict detection against source baseline."""

    def test_no_conflict_when_source_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "stable.txt").write_text("unchanged")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            conflicts = detect_conflicts(snap)
            self.assertEqual(conflicts, [])

    def test_detects_modified_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data.txt").write_text("original")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Modify the source file after snapshot.
            (source / "data.txt").write_text("modified externally")

            conflicts = detect_conflicts(snap)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].kind, ConflictKind.FILE_MODIFIED)
            self.assertEqual(conflicts[0].path, "data.txt")

    def test_detects_deleted_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "gone.txt").write_text("will be deleted")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Delete the source file.
            (source / "gone.txt").unlink()

            conflicts = detect_conflicts(snap)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].kind, ConflictKind.FILE_DELETED)
            self.assertEqual(conflicts[0].path, "gone.txt")

    def test_detects_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "existing.txt").write_text("I exist")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Create a new file in source.
            (source / "new_in_source.txt").write_text("added later")

            conflicts = detect_conflicts(snap)
            created = [c for c in conflicts if c.kind == ConflictKind.FILE_CREATED]
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].path, "new_in_source.txt")

    def test_detects_multiple_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "a.txt").write_text("a")
            (source / "b.txt").write_text("b")
            (source / "c.txt").write_text("c")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Modify a, delete b, create d.
            (source / "a.txt").write_text("A")
            (source / "b.txt").unlink()
            (source / "d.txt").write_text("d")

            conflicts = detect_conflicts(snap)
            kinds = {c.kind for c in conflicts}
            self.assertIn(ConflictKind.FILE_MODIFIED, kinds)
            self.assertIn(ConflictKind.FILE_DELETED, kinds)
            self.assertIn(ConflictKind.FILE_CREATED, kinds)

    def test_detects_regular_file_replaced_by_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            target = source / "target.txt"
            target.write_text("outside")
            path = source / "data.txt"
            path.write_text("baseline")
            snap = create_integration_snapshot(
                source, graph_id="g1", parent_dir=Path(tmp) / "snap"
            ).snapshot
            path.unlink()
            try:
                path.symlink_to(target)
            except OSError:
                self.skipTest("Cannot create symlinks in this environment")
            conflicts = detect_conflicts(snap, paths={"data.txt"})
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].kind, ConflictKind.FILE_MODIFIED)

    def test_default_scan_ignores_snapshot_excluded_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data.txt").write_text("baseline")
            snap = create_integration_snapshot(
                source, graph_id="g1", parent_dir=Path(tmp) / "snap"
            ).snapshot
            (source / ".c4harness").mkdir()
            (source / ".c4harness" / "ledger.sqlite3").write_text("runtime")
            self.assertEqual(detect_conflicts(snap), [])


class OverlappingReservationTests(unittest.TestCase):
    """Tests for write-set reservation conflict detection."""

    def test_same_path_conflicts(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["src/main.py"])

    def test_prefix_overlap_conflicts(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/"])
        # src/main.py is under src/, so this should conflict.
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["src/main.py"])

    def test_reverse_prefix_overlap_conflicts(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        # src/ is a parent of src/main.py.
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["src/"])

    def test_disjoint_paths_no_conflict(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        mgr.reserve("node-2", ["lib/utils.py"])
        # Should not raise.

    def test_same_node_idempotent(self) -> None:
        mgr = WriteReservationManager()
        recs1 = mgr.reserve("node-1", ["src/main.py"])
        recs2 = mgr.reserve("node-1", ["src/main.py"])
        # Second reserve for same node/path is a no-op.
        self.assertEqual(recs2, [])

    def test_release_frees_path(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        mgr.release("node-1", "src/main.py")
        # Now node-2 can reserve it.
        mgr.reserve("node-2", ["src/main.py"])

    def test_release_node_releases_all(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["a.py", "b.py", "c.py"])
        released = mgr.release_node("node-1")
        self.assertEqual(released, 3)
        self.assertEqual(mgr.node_paths("node-1"), set())
        # Other nodes can now reserve these paths.
        mgr.reserve("node-2", ["a.py"])

    def test_all_or_nothing_reserve(self) -> None:
        """If one path conflicts, none are reserved."""
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["lib/ok.py", "src/main.py"])
        # lib/ok.py should NOT be reserved (all-or-nothing).
        self.assertIsNone(mgr.is_reserved("lib/ok.py"))

    def test_detect_conflicts_with_reservations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "f.txt").write_text("data")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Disjoint reservations produce no WRITE_CONFLICT.
            mgr = WriteReservationManager()
            mgr.reserve("node-1", ["src/"])
            mgr.reserve("node-2", ["lib/"])
            conflicts = detect_conflicts(snap, reservation_manager=mgr)
            write_conflicts = [
                c for c in conflicts if c.kind == ConflictKind.WRITE_CONFLICT
            ]
            self.assertEqual(write_conflicts, [])

    def test_overlapping_reservations_raises(self) -> None:
        """Prefix-overlapping reservations from different nodes raise."""
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/"])
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["src/main.py"])

    def test_overlapping_reservations_reverse_raises(self) -> None:
        """Reverse prefix overlap also raises."""
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/main.py"])
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["src/"])

    def test_same_path_reservation_raises(self) -> None:
        """Exact same path from different nodes raises."""
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["f.txt"])
        with self.assertRaises(ValueError):
            mgr.reserve("node-2", ["f.txt"])


class SourceUnchangedTests(unittest.TestCase):
    """Proof that source files remain unchanged after all operations."""

    def test_source_files_unchanged_after_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            files = {
                "main.py": "print('hello')\n",
                "lib/utils.py": "x = 42\n",
                "config.yaml": "key: value\n",
                ".env": "SECRET=abc\n",
            }
            for name, content in files.items():
                p = source / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)

            # Record SHA-256 of all source files before.
            before_hashes = _file_hashes(source)

            # Create snapshot.
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Apply patches to the snapshot.
            applier = PatchApplier(snap, allowed_paths={
                "main.py", "lib/utils.py", "config.yaml", "new_file.txt",
            })
            hunks = [
                PatchHunk(
                    path="main.py",
                    kind=ChangeKind.MODIFY,
                    content="print('changed')\n",
                ),
                PatchHunk(
                    path="lib/utils.py",
                    kind=ChangeKind.DELETE,
                ),
                PatchHunk(
                    path="new_file.txt",
                    kind=ChangeKind.CREATE,
                    content="brand new\n",
                ),
            ]
            patch_result = applier.apply(hunks)
            self.assertTrue(patch_result.success)

            # Verify source is UNCHANGED.
            after_hashes = _file_hashes(source)
            self.assertEqual(before_hashes, after_hashes)

            # Verify specific files.
            self.assertEqual(
                (source / "main.py").read_text(), "print('hello')\n"
            )
            self.assertEqual(
                (source / "lib" / "utils.py").read_text(), "x = 42\n"
            )
            self.assertTrue((source / "config.yaml").exists())

    def test_source_unchanged_after_conflict_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data.txt").write_text("original\n")

            before = _file_hashes(source)

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            # Run conflict detection (read-only operation).
            _ = detect_conflicts(snap)

            after = _file_hashes(source)
            self.assertEqual(before, after)

    def test_source_unchanged_after_reservation_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "f.txt").write_text("content\n")

            before = _file_hashes(source)

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot

            mgr = WriteReservationManager()
            mgr.reserve("node-1", ["f.txt"])
            mgr.reserve("node-2", ["other.txt"])
            mgr.release_node("node-1")
            mgr.release_node("node-2")

            _ = detect_conflicts(snap, reservation_manager=mgr)

            after = _file_hashes(source)
            self.assertEqual(before, after)


class IntegrationResultSerializationTests(unittest.TestCase):
    """Tests for to_dict() methods on result types."""

    def test_file_state_to_dict(self) -> None:
        fs = FileState(path="a.txt", sha256="abc123", size=100)
        d = fs.to_dict()
        self.assertEqual(d["path"], "a.txt")
        self.assertEqual(d["sha256"], "abc123")
        self.assertEqual(d["size"], 100)

    def test_integration_result_to_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "f.txt").write_text("x")
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            d = result.to_dict()
            self.assertTrue(d["success"])
            self.assertEqual(d["copied_files"], 1)

    def test_patch_result_to_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            applier = PatchApplier(snap)
            hunks = [PatchHunk(
                path="new.txt",
                kind=ChangeKind.CREATE,
                content="hello",
            )]
            pr = applier.apply(hunks)
            d = pr.to_dict()
            self.assertTrue(d["success"])
            self.assertEqual(d["applied_count"], 1)

    def test_conflict_to_dict(self) -> None:
        c = Conflict(
            path="f.txt",
            kind=ConflictKind.FILE_MODIFIED,
            baseline_sha256="aaa",
            source_sha256="bbb",
            detail="changed",
        )
        d = c.to_dict()
        self.assertEqual(d["kind"], "file_modified")


class SnapshotMetadataTests(unittest.TestCase):
    """Tests for snapshot metadata and helper methods."""

    def test_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "a.txt").write_text("a")
            (source / "b.txt").write_text("b")
            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            paths = snap.relative_paths()
            self.assertIn("a.txt", paths)
            self.assertIn("b.txt", paths)

    def test_snapshot_to_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "f.txt").write_text("x")
            result = create_integration_snapshot(
                source, graph_id="g-test", node_id="n-test",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            d = snap.to_dict()
            self.assertEqual(d["graph_id"], "g-test")
            self.assertEqual(d["node_id"], "n-test")
            self.assertEqual(d["file_count"], 1)


class WriteReservationEdgeCaseTests(unittest.TestCase):
    """Additional edge cases for write reservations."""

    def test_empty_paths_list(self) -> None:
        mgr = WriteReservationManager()
        recs = mgr.reserve("node-1", [])
        self.assertEqual(recs, [])

    def test_release_nonexistent(self) -> None:
        mgr = WriteReservationManager()
        released = mgr.release("node-1", "nonexistent.py")
        self.assertFalse(released)

    def test_release_node_empty(self) -> None:
        mgr = WriteReservationManager()
        released = mgr.release_node("node-1")
        self.assertEqual(released, 0)

    def test_is_reserved_returns_none_for_free_path(self) -> None:
        mgr = WriteReservationManager()
        self.assertIsNone(mgr.is_reserved("free.py"))

    def test_is_reserved_returns_record_for_reserved_path(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["taken.py"])
        rec = mgr.is_reserved("taken.py")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.node_id, "node-1")
        self.assertFalse(rec.released)

    def test_node_paths(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["a.py", "b.py"])
        mgr.reserve("node-2", ["c.py"])
        self.assertEqual(mgr.node_paths("node-1"), {"a.py", "b.py"})
        self.assertEqual(mgr.node_paths("node-2"), {"c.py"})
        self.assertEqual(mgr.node_paths("node-3"), set())

    def test_all_records_includes_released(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["a.py"])
        mgr.release("node-1", "a.py")
        records = mgr.all_records
        self.assertEqual(len(records), 2)
        self.assertFalse(records[0].released)
        self.assertTrue(records[1].released)

    def test_release_and_query_canonicalize_directory_paths(self) -> None:
        mgr = WriteReservationManager()
        mgr.reserve("node-1", ["src/"])
        self.assertEqual(mgr.is_reserved("src/main.py").node_id, "node-1")
        self.assertTrue(mgr.release("node-1", "src/"))
        self.assertIsNone(mgr.is_reserved("src/main.py"))

    def test_reservation_record_to_dict(self) -> None:
        from c4harness.integrator import ReservationRecord
        rec = ReservationRecord(node_id="n1", path="a.py", released=False)
        d = rec.to_dict()
        self.assertEqual(d["node_id"], "n1")
        self.assertEqual(d["path"], "a.py")
        self.assertFalse(d["released"])


class NestedDirectoryTests(unittest.TestCase):
    """Tests for deeply nested directory structures."""

    def test_deep_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            deep = source / "a" / "b" / "c" / "d"
            deep.mkdir(parents=True)
            (deep / "deep.txt").write_text("deep content")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            self.assertIn("a/b/c/d/deep.txt", snap.file_states)
            self.assertEqual(
                (snap.root / "a" / "b" / "c" / "d" / "deep.txt").read_text(),
                "deep content",
            )

    def test_mixed_files_and_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "top.txt").write_text("top")
            (source / "sub").mkdir()
            (source / "sub" / "mid.txt").write_text("mid")
            (source / "sub" / "deep").mkdir()
            (source / "sub" / "deep" / "bottom.txt").write_text("bottom")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            snap = result.snapshot
            self.assertEqual(len(snap.file_states), 3)
            self.assertIn("top.txt", snap.file_states)
            self.assertIn("sub/mid.txt", snap.file_states)
            self.assertIn("sub/deep/bottom.txt", snap.file_states)


class EmptySourceTests(unittest.TestCase):
    """Tests for snapshotting an empty directory."""

    def test_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "empty"
            source.mkdir()

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            self.assertTrue(result.success)
            self.assertEqual(result.copied_files, 0)
            snap = result.snapshot
            self.assertEqual(len(snap.file_states), 0)

    def test_source_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "not_a_dir.txt"
            source.write_text("I'm a file")

            result = create_integration_snapshot(
                source, graph_id="g1", node_id="n1",
                parent_dir=Path(tmp) / "snap",
            )
            self.assertFalse(result.success)
            self.assertTrue(result.errors)


class UnifiedPatchAndGraphSessionTests(unittest.TestCase):
    def test_real_proposed_patch_is_applied_and_can_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo"
            source.mkdir()
            (source / "a.txt").write_text("old\n", encoding="utf-8")
            session = GraphIntegrationSession.create(
                source,
                graph_id="graph-1",
                parent_dir=root / "runs",
            )
            patch = root / "proposed.patch"
            patch.write_text(
                "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
                "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+created\n",
                encoding="utf-8",
            )
            attempt = session.apply_proposal(
                patch_path=patch,
                write_paths=(source / "a.txt", source / "new.txt"),
            )
            self.assertTrue(attempt.accepted, attempt.issues)
            self.assertEqual((session.root / "a.txt").read_text(), "new\n")
            self.assertEqual((session.root / "new.txt").read_text(), "created\n")
            self.assertEqual((source / "a.txt").read_text(), "old\n")
            self.assertFalse((source / "new.txt").exists())
            self.assertTrue(session.rollback(attempt))
            self.assertEqual((session.root / "a.txt").read_text(), "old\n")
            self.assertFalse((session.root / "new.txt").exists())

    def test_sequential_nodes_share_one_workspace_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plain-directory"
            source.mkdir()
            (source / "state.txt").write_text("v1\n")
            session = GraphIntegrationSession.create(
                source,
                graph_id="graph-1",
                parent_dir=root / "runs",
            )
            first_root = session.root
            patch = root / "proposed.patch"
            patch.write_text(
                "--- a/state.txt\n+++ b/state.txt\n@@ -1 +1 @@\n-v1\n+v2\n",
                encoding="utf-8",
            )
            attempt = session.apply_proposal(
                patch_path=patch,
                write_paths=(source / "state.txt",),
            )
            self.assertTrue(attempt.accepted)
            session.commit(attempt)
            self.assertEqual(session.root, first_root)
            self.assertEqual((session.root / "state.txt").read_text(), "v2\n")

    def test_source_change_blocks_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "repo"
            source.mkdir()
            (source / "a.txt").write_text("old\n")
            session = GraphIntegrationSession.create(
                source,
                graph_id="graph-1",
                parent_dir=root / "runs",
            )
            (source / "a.txt").write_text("external\n")
            patch = root / "proposed.patch"
            patch.write_text(
                "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+worker\n"
            )
            attempt = session.apply_proposal(
                patch_path=patch,
                write_paths=(source / "a.txt",),
            )
            self.assertFalse(attempt.accepted)
            self.assertTrue(attempt.conflicts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_hashes(directory: Path) -> dict[str, str]:
    """Return SHA-256 hashes of all files in *directory*."""
    hashes: dict[str, str] = {}
    for entry in directory.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            relative = entry.relative_to(directory).as_posix()
            hashes[relative] = hashlib.sha256(
                entry.read_bytes()
            ).hexdigest()
    return hashes


if __name__ == "__main__":
    unittest.main()
