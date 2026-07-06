from __future__ import annotations

import json
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from contextlib import redirect_stdout

from cost_router.delegator.async_runtime import (
    AsyncTaskConfig,
    AsyncTaskRuntime,
    AsyncTaskStore,
    retry_callbacks,
)
from cost_router.cli import main


def executable(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


class AsyncTaskTests(unittest.TestCase):
    def test_cli_start_detaches_controller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.sqlite3"
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "async-task",
                        "start",
                        "--goal",
                        "detached CLI job",
                        "--repo",
                        str(root),
                        "--command",
                        f"{sys.executable} -c \"import time; print(42); time.sleep(.2)\"",
                        "--backend",
                        "none",
                        "--callback",
                        "none",
                        "--interval",
                        "0.05",
                        "--memory",
                        str(memory),
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            store = AsyncTaskStore(memory)
            deadline = time.time() + 5
            while time.time() < deadline:
                record = store.get(payload["id"])
                if record and record["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            record = store.get(payload["id"])
            assert record is not None
            self.assertEqual(record["status"], "completed")

    def test_generic_workload_completes_without_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.sqlite3"
            config = AsyncTaskConfig(
                goal="finish a generic background job",
                repo=root,
                workload_command=[sys.executable, "-c", "print('finished')"],
                backend="none",
                interval_sec=0.05,
            )
            store = AsyncTaskStore(memory)
            store.create(config)

            self.assertEqual(AsyncTaskRuntime(memory, config.id).run(), 0)
            record = store.get(config.id)
            assert record is not None
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["workload_exit_code"], 0)
            events = store.events(config.id)
            self.assertEqual(
                len([item for item in events if item["event_type"] == "task.completed"]), 1
            )
            workload_log = memory.parent / "async-tasks" / config.id / "workload.log"
            self.assertIn("finished", workload_log.read_text(encoding="utf-8"))

    def test_claude_session_is_resumed_and_completion_wakes_codex_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.sqlite3"
            claude_trace = root / "claude-trace.jsonl"
            codex_trace = root / "codex-trace.jsonl"
            fake_claude = executable(
                root / "fake-claude",
                f"""
                #!{sys.executable}
                import json, pathlib, sys
                trace = pathlib.Path({str(claude_trace)!r})
                with trace.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(sys.argv[1:]) + '\\n')
                prompt = sys.argv[-1]
                status = 'completed' if 'terminal:task.completed' in prompt else 'running'
                print(json.dumps({{
                    'structured_output': {{
                        'status': status,
                        'summary': 'workload complete' if status == 'completed' else 'workload progressing',
                        'recommended_action': 'report completion' if status == 'completed' else 'keep watching'
                    }},
                    'usage': {{'input_tokens': 20, 'output_tokens': 5}}
                }}))
                """,
            )
            fake_codex = executable(
                root / "fake-codex",
                f"""
                #!{sys.executable}
                import json, pathlib, sys
                trace = pathlib.Path({str(codex_trace)!r})
                with trace.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(sys.argv[1:]) + '\\n')
                print('callback accepted')
                """,
            )
            config = AsyncTaskConfig(
                goal="run a long generic job",
                repo=root,
                workload_command=[sys.executable, "-c", "import time; print('working'); time.sleep(.3)"],
                backend="claude_cli",
                interval_sec=0.05,
                source_thread_id="thread-test",
                source_harness="codex",
                callback_mode="codex_resume",
                claude_command=str(fake_claude),
                codex_command=str(fake_codex),
            )
            store = AsyncTaskStore(memory)
            store.create(config)

            self.assertEqual(AsyncTaskRuntime(memory, config.id).run(), 0)
            calls = [json.loads(line) for line in claude_trace.read_text().splitlines()]
            self.assertGreaterEqual(len(calls), 2)
            self.assertIn("--session-id", calls[0])
            self.assertTrue(any("--resume" in call for call in calls[1:]))

            callbacks = [json.loads(line) for line in codex_trace.read_text().splitlines()]
            self.assertEqual(len(callbacks), 1)
            self.assertEqual(callbacks[0][:3], ["exec", "resume", "thread-test"])
            self.assertIn("task.completed", callbacks[0][3])

            events = store.events(config.id)
            completed = [item for item in events if item["event_type"] == "task.completed"]
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0]["callback_status"], "delivered")
            self.assertEqual(retry_callbacks(memory, config.id), (0, 0))

            with sqlite3.connect(memory) as conn:
                monitor_calls = conn.execute(
                    "SELECT COUNT(*) FROM subtasks WHERE worker = 'claude_async_session'"
                ).fetchone()[0]
            self.assertEqual(monitor_calls, len(calls))

    def test_failed_workload_emits_failed_terminal_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.sqlite3"
            config = AsyncTaskConfig(
                goal="observe a failing job",
                repo=root,
                workload_command=[sys.executable, "-c", "raise SystemExit(7)"],
                backend="none",
                interval_sec=0.05,
            )
            store = AsyncTaskStore(memory)
            store.create(config)

            self.assertEqual(AsyncTaskRuntime(memory, config.id).run(), 1)
            record = store.get(config.id)
            assert record is not None
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["workload_exit_code"], 7)
            self.assertTrue(
                any(item["event_type"] == "task.failed" for item in store.events(config.id))
            )

    def test_stop_request_cancels_running_workload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.sqlite3"
            config = AsyncTaskConfig(
                goal="cancel a background job",
                repo=root,
                workload_command=[sys.executable, "-c", "import time; time.sleep(30)"],
                backend="none",
                interval_sec=0.05,
            )
            store = AsyncTaskStore(memory)
            store.create(config)
            thread = threading.Thread(target=AsyncTaskRuntime(memory, config.id).run)
            thread.start()
            deadline = time.time() + 3
            while time.time() < deadline:
                record = store.get(config.id)
                if record and record["workload_pid"]:
                    break
                time.sleep(0.02)
            self.assertTrue(store.request_stop(config.id))
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            record = store.get(config.id)
            assert record is not None
            self.assertEqual(record["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
