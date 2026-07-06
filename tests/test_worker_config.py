from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.config.workers import WorkerManifestStore, builtin_workers


class WorkerManifestTests(unittest.TestCase):
    def test_defaults_save_atomically_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkerManifestStore(Path(tmp) / "workers.json")
            document = store.load_document()
            saved = store.save(document, expected_revision=document["revision"])
            self.assertEqual(store.load_document(), saved)
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            workers, _ = store.registry()
            self.assertEqual(workers["claude-cli-sonnet"].model_alias, "sonnet")

    def test_legacy_manifest_receives_model_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkerManifestStore(Path(tmp) / "workers.json")
            document = store.load_document()
            for worker in document["workers"]:
                worker.pop("model_alias", None)
            saved = store.save(document, expected_revision=document["revision"])
            self.assertEqual(saved["workers"][0]["model_alias"], saved["workers"][0]["model"])

    def test_known_harness_derives_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkerManifestStore(Path(tmp) / "workers.json")
            document = store.load_document()
            document["workers"][0]["backend"] = "codex_subagent"
            saved = store.save(document, expected_revision=document["revision"])
            self.assertEqual(saved["workers"][0]["backend"], "claude_cli")

    def test_revision_conflict_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkerManifestStore(Path(tmp) / "workers.json")
            document = store.load_document()
            store.save(document, expected_revision=document["revision"])
            with self.assertRaisesRegex(ValueError, "revision conflict"):
                store.save(document, expected_revision="stale")
            duplicate = {"version": 1, "workers": [builtin_workers()[0], builtin_workers()[0]]}
            with self.assertRaisesRegex(ValueError, "duplicate worker"):
                store.save(duplicate, expected_revision=store.load_document()["revision"])

    def test_secret_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkerManifestStore(Path(tmp) / "workers.json")
            document = store.load_document()
            document["workers"][0]["api_key"] = "secret"
            with self.assertRaises(ValueError):
                store.save(document, expected_revision=document["revision"])


if __name__ == "__main__":
    unittest.main()
