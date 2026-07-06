from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cost_router.usage.aggregation import AnalyticsStore
from cost_router.dashboard.server import _handler
from cost_router.memory import MemoryStore
from cost_router.config.paths import default_memory_path
from cost_router.core.contracts import (
    Difficulty,
    Risk,
    RouteDecision,
    Task,
    TokenAnalysis,
    TokenUsage,
    VerificationResult,
    WorkerResult,
)
from cost_router.setup_user import setup_user
from cost_router.delegator.async_runtime import AsyncTaskConfig, AsyncTaskStore


def decision(backend: str, model: str = "test-model") -> RouteDecision:
    return RouteDecision(
        difficulty=Difficulty.SIMPLE,
        risk=Risk.READ_ONLY,
        can_delegate=True,
        backend=backend,
        worker=backend,
        model=model,
        reason=f"route to {backend}",
    )


def result(total: int | None, delegated: int = 1000, saved: int = 800) -> WorkerResult:
    return WorkerResult(
        status="success",
        summary="Completed delegated analysis.",
        token_usage=TokenUsage(total_tokens=total, source="test" if total else None),
        token_analysis=TokenAnalysis(
            delegated_context_tokens_estimate=delegated,
            returned_result_tokens_estimate=delegated - saved,
            estimated_main_tokens_saved=saved,
        ),
    )


class DashboardTests(unittest.TestCase):
    def test_global_path_override_and_codex_thread_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"COST_ROUTER_MEMORY": f"{tmp}/ledger.sqlite3", "CODEX_THREAD_ID": "thread-42"},
        ):
            self.assertEqual(default_memory_path(), Path(tmp) / "ledger.sqlite3")
            task = Task(goal="worker task", parent_task_label="parent task")
            self.assertEqual(task.source_thread_id, "thread-42")
            self.assertEqual(task.source_harness, "codex")

    def test_legacy_schema_is_migrated_and_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            with sqlite3.connect(path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE runs (id TEXT PRIMARY KEY, goal TEXT NOT NULL, repo TEXT NOT NULL,
                                       created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                    CREATE TABLE subtasks (
                      id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                      backend TEXT NOT NULL, worker TEXT NOT NULL, model TEXT NOT NULL,
                      decision_json TEXT NOT NULL, result_json TEXT, verification_json TEXT,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute("INSERT INTO runs (id, goal, repo) VALUES ('old', 'legacy task', '/repo')")
                conn.execute(
                    "INSERT INTO subtasks (run_id, backend, worker, model, decision_json, result_json, verification_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "old", "claude_cli", "claude_cli", "sonnet",
                        json.dumps({"risk": "read_only", "reason": "legacy"}),
                        json.dumps({
                            "status": "success",
                            "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                            "token_analysis": {
                                "delegated_context_tokens_estimate": 100,
                                "returned_result_tokens_estimate": 20,
                                "estimated_main_tokens_saved": 80,
                            },
                        }),
                        json.dumps({"accepted": True}),
                    ),
                )
            MemoryStore(path).init()
            with sqlite3.connect(path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(subtasks)")}
                row = conn.execute(
                    "SELECT executed, accepted, total_tokens, estimated_main_tokens_saved FROM subtasks"
                ).fetchone()
            self.assertIn("delegated_context_tokens_estimate", columns)
            self.assertEqual(row, (1, 1, 15, 80))

    def test_analytics_grouping_filters_and_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analytics.sqlite3"
            store = MemoryStore(path)
            verification = VerificationResult(accepted=True, confidence="high")
            first = Task(
                goal="inspect logs",
                repo=Path("/projects/alpha"),
                parent_task_label="Fix evaluation",
                source_thread_id="thread-alpha",
                source_harness="codex",
            )
            store.record_subtask(
                task=first,
                decision=decision("claude_cli", "sonnet"),
                result=result(250, 1200, 900),
                verification=verification,
            )
            second = Task(
                goal="search repository",
                repo=Path("/projects/beta"),
                parent_task_label="Review router",
                source_thread_id="thread-beta",
                source_harness="codex",
            )
            store.record_subtask(
                task=second,
                decision=decision("codex_subagent", "qwen"),
                result=result(None, 600, 450),
                verification=verification,
            )

            analytics = AnalyticsStore(path)
            overview = analytics.overview("all", "Asia/Shanghai")
            self.assertEqual(overview["totals"]["calls"], 2)
            self.assertEqual(overview["totals"]["worker_tokens"], 250)
            self.assertEqual(overview["totals"]["actual_token_calls"], 1)
            self.assertEqual(overview["totals"]["saved_tokens"], 1350)
            self.assertTrue(any(item["backend"] == "opencode" for item in overview["providers"]))

            series = analytics.timeseries("30d", "day", "delegated_tokens", "Asia/Shanghai")
            self.assertGreaterEqual(len(series["points"]), 30)
            self.assertEqual(sum(sum(point["values"].values()) for point in series["points"]), 1800)

            calls = analytics.calls(range_name="all", backend="claude_cli", query="Fix")
            self.assertEqual(calls["total"], 1)
            self.assertEqual(calls["items"][0]["source_thread_id"], "thread-alpha")
            detail = analytics.call_detail(calls["items"][0]["id"])
            self.assertEqual(detail["route_reason"], "route to claude_cli")
            self.assertEqual(detail["summary"], "Completed delegated analysis.")

    def test_dashboard_http_api_and_static_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "http.sqlite3"
            MemoryStore(path).init()
            async_store = AsyncTaskStore(path)
            async_config = AsyncTaskConfig(
                goal="review completed evaluation",
                repo=Path(tmp),
                workload_command=["true"],
                backend="none",
                source_thread_id="thread-dashboard",
            )
            async_store.create(async_config)
            async_store.update(async_config.id, status="completed")
            async_store.record_event(
                async_config.id,
                "task.completed",
                "task.completed",
                {"status": "completed", "summary": "evaluation finished"},
                request_inbox=True,
            )
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(AnalyticsStore(path)))
            except PermissionError:
                self.skipTest("local sockets are disabled by the test sandbox")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base, timeout=2) as response:
                    page = response.read().decode("utf-8")
                with urlopen(f"{base}/c4.png", timeout=2) as response:
                    icon = response.read()
                with urlopen(f"{base}/api/metadata", timeout=2) as response:
                    metadata = json.load(response)
                with urlopen(f"{base}/api/overview?range=all", timeout=2) as response:
                    payload = json.load(response)
                with urlopen(f"{base}/api/async-tasks", timeout=2) as response:
                    async_payload = json.load(response)
                self.assertIn("C4Harness Console", page)
                self.assertTrue(icon.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertTrue(metadata["csrf_token"])
                self.assertTrue(metadata["worker_config_write_enabled"])
                self.assertEqual(payload["totals"]["calls"], 0)
                self.assertEqual(async_payload["summary"]["unread_tasks"], 1)
                self.assertEqual(async_payload["groups"][0]["thread_id"], "thread-dashboard")
                blocked = Request(
                    f"{base}/api/async-tasks/{async_config.id}/ack", method="PUT"
                )
                with self.assertRaises(HTTPError) as caught:
                    urlopen(blocked, timeout=2)
                self.assertEqual(caught.exception.code, 403)
                acknowledged = Request(
                    f"{base}/api/async-tasks/{async_config.id}/ack",
                    method="PUT",
                    headers={"X-C4-CSRF": metadata["csrf_token"]},
                )
                with urlopen(acknowledged, timeout=2) as response:
                    ack_payload = json.load(response)
                self.assertEqual(ack_payload["acknowledged"], 1)
            finally:
                server.shutdown()
                server.server_close()

    def test_user_setup_installs_and_updates_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"HOME": tmp, "XDG_DATA_HOME": f"{tmp}/data"},
            clear=False,
        ):
            os.environ.pop("COST_ROUTER_MEMORY", None)
            first = setup_user()
            skill = Path(first["skill_path"]) / "SKILL.md"
            self.assertEqual(first["skill_status"], "installed")
            self.assertTrue(Path(first["memory_path"]).exists())
            self.assertTrue(skill.exists())
            skill.write_text("local change", encoding="utf-8")
            self.assertEqual(setup_user()["skill_status"], "kept")
            self.assertEqual(skill.read_text(encoding="utf-8"), "local change")
            updated = setup_user(force=True)
            self.assertEqual(updated["skill_status"], "updated")
            self.assertIn("name: cost-router", skill.read_text(encoding="utf-8"))
            self.assertIn(str(Path(tmp) / "data" / "cost-router"), updated["codex_config"])

    def test_bundled_skill_is_self_contained(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bundled = root / "cost_router/bundled_skill"
        skill_text = (bundled / "SKILL.md").read_text(encoding="utf-8")
        agent_text = (bundled / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("name: cost-router", skill_text)
        self.assertIn("### Risk Disclosure and Consent", skill_text)
        self.assertIn("Wait for explicit user approval", skill_text)
        self.assertIn("Codex is not automatically awakened", skill_text)
        self.assertIn("Retry the same bounded operation once", skill_text)
        self.assertIn('display_name: "Cost Router"', agent_text)


if __name__ == "__main__":
    unittest.main()
