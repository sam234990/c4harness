from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cost_router.config.workers import WorkerManifestStore
from cost_router.dashboard.server import _handler
from cost_router.memory import MemoryStore
from cost_router.usage.aggregation import AnalyticsStore


class WorkerDashboardTests(unittest.TestCase):
    def test_worker_page_has_visible_save_feedback(self) -> None:
        root = Path(__file__).resolve().parents[1] / "cost_router" / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        javascript = (root / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="workers-save-status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('button.textContent = t("savingConfig")', javascript)
        self.assertIn('const confirmed = await api("/api/workers")', javascript)

    def test_worker_manifest_http_round_trip_and_csrf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite3"
            manifest = Path(tmp) / "workers.json"
            MemoryStore(ledger).init()
            try:
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    _handler(AnalyticsStore(ledger), worker_store=WorkerManifestStore(manifest)),
                )
            except PermissionError:
                self.skipTest("local sockets are disabled by the test sandbox")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(f"{base}/api/workers", timeout=2) as response:
                    document = json.load(response)
                self.assertTrue(document["write_enabled"])
                document["workers"][0]["preference_bias"] = 0.25
                payload = {
                    "version": document["version"],
                    "revision": document["revision"],
                    "workers": document["workers"],
                }
                request = Request(
                    f"{base}/api/workers",
                    data=json.dumps(payload).encode(),
                    method="PUT",
                    headers={
                        "Content-Type": "application/json",
                        "X-C4-CSRF": document["csrf_token"],
                    },
                )
                with urlopen(request, timeout=2) as response:
                    saved = json.load(response)
                self.assertEqual(saved["workers"][0]["preference_bias"], 0.25)
                self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)

                stale = Request(
                    f"{base}/api/workers",
                    data=json.dumps(payload).encode(),
                    method="PUT",
                    headers={
                        "Content-Type": "application/json",
                        "X-C4-CSRF": document["csrf_token"],
                    },
                )
                with self.assertRaises(HTTPError) as caught:
                    urlopen(stale, timeout=2)
                self.assertEqual(caught.exception.code, 409)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
