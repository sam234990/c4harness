from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ..core.contracts import (
    Difficulty,
    Risk,
    RouteDecision,
    Task,
    TokenAnalysis,
    WorkerResult,
)
from ..memory import MemoryStore
from ..usage import extract_token_usage


TERMINAL_STATES = {"completed", "failed", "cancelled", "timed_out"}
CALLBACK_EVENT_TYPES = {
    "task.completed",
    "task.failed",
    "task.cancelled",
    "task.timed_out",
    "worker.needs_input",
    "worker.stalled",
    "worker.reported_failure",
}


@dataclass(slots=True)
class AsyncTaskConfig:
    goal: str
    repo: Path
    workload_command: list[str]
    log_paths: list[Path] = field(default_factory=list)
    backend: str = "claude_cli"
    model: str | None = None
    interval_sec: float = 60.0
    max_runtime_sec: int | None = None
    success_file: Path | None = None
    failure_file: Path | None = None
    source_thread_id: str | None = None
    source_harness: str = "cli"
    callback_mode: str = "none"
    claude_command: str = "claude"
    codex_command: str = "codex"
    external_policy: str = "ask"
    data_classification: str = "private"
    id: str = field(default_factory=lambda: f"async_{uuid4().hex[:12]}")

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "repo": str(self.repo),
            "backend": self.backend,
            "model": self.model,
            "workload_command_json": json.dumps(self.workload_command),
            "log_paths_json": json.dumps([str(path) for path in self.log_paths]),
            "interval_sec": self.interval_sec,
            "max_runtime_sec": self.max_runtime_sec,
            "success_file": str(self.success_file) if self.success_file else None,
            "failure_file": str(self.failure_file) if self.failure_file else None,
            "source_thread_id": self.source_thread_id,
            "source_harness": self.source_harness,
            "callback_mode": self.callback_mode,
            "claude_command": self.claude_command,
            "codex_command": self.codex_command,
            "external_policy": self.external_policy,
            "data_classification": self.data_classification,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "AsyncTaskConfig":
        return cls(
            id=record["id"],
            goal=record["goal"],
            repo=Path(record["repo"]),
            backend=record["backend"],
            model=record.get("model"),
            workload_command=list(json.loads(record["workload_command_json"])),
            log_paths=[Path(item) for item in json.loads(record["log_paths_json"])],
            interval_sec=float(record["interval_sec"]),
            max_runtime_sec=record.get("max_runtime_sec"),
            success_file=Path(record["success_file"]) if record.get("success_file") else None,
            failure_file=Path(record["failure_file"]) if record.get("failure_file") else None,
            source_thread_id=record.get("source_thread_id"),
            source_harness=record.get("source_harness") or "cli",
            callback_mode=record.get("callback_mode") or "none",
            claude_command=record.get("claude_command") or "claude",
            codex_command=record.get("codex_command") or "codex",
            external_policy=record.get("external_policy") or "ask",
            data_classification=record.get("data_classification") or "private",
        )


@dataclass(slots=True)
class WorkerObservation:
    status: str
    summary: str
    recommended_action: str = ""
    token_usage: Any = None


@dataclass(slots=True)
class CallbackOutcome:
    """Result of notifying a host about an inbox event.

    ``callback_executed`` means only that a compatibility command exited
    successfully.  ``acknowledged`` is reserved for adapters that receive an
    explicit acknowledgement from the host displaying the conversation.
    """

    status: str
    error: str | None = None
    output: str = ""


class CallbackNotifier(Protocol):
    def notify(
        self, config: "AsyncTaskConfig", event: dict[str, Any], message: str
    ) -> CallbackOutcome: ...


class AsyncTaskStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        MemoryStore(path).init()

    def create(self, config: AsyncTaskConfig) -> None:
        values = config.to_record()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO async_tasks (
                  id, goal, repo, backend, model, workload_command_json, log_paths_json,
                  interval_sec, max_runtime_sec, success_file, failure_file,
                  source_thread_id, source_harness, callback_mode,
                  claude_command, codex_command, external_policy, data_classification
                ) VALUES (
                  :id, :goal, :repo, :backend, :model, :workload_command_json,
                  :log_paths_json, :interval_sec, :max_runtime_sec, :success_file,
                  :failure_file, :source_thread_id, :source_harness, :callback_mode,
                  :claude_command, :codex_command, :external_policy, :data_classification
                )
                """,
                values,
            )

    def get(self, task_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM async_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def claim(self, task_id: str, runtime_pid: int) -> bool:
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                UPDATE async_tasks
                SET status = 'running', runtime_pid = ?, started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
                """,
                (runtime_pid, task_id),
            )
        return cursor.rowcount == 1

    def update(self, task_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "worker_session_id",
            "runtime_pid",
            "workload_pid",
            "workload_exit_code",
            "last_worker_summary",
            "stop_requested",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported async task fields: {sorted(unknown)}")
        if not fields:
            return
        assignments = [f"{name} = ?" for name in fields]
        if fields.get("status") in TERMINAL_STATES:
            assignments.append("finished_at = CURRENT_TIMESTAMP")
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        values = [*fields.values(), task_id]
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"UPDATE async_tasks SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

    def request_stop(self, task_id: str) -> bool:
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                UPDATE async_tasks
                SET stop_requested = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'cancelled', 'timed_out')
                """,
                (task_id,),
            )
        return cursor.rowcount == 1

    def record_event(
        self,
        task_id: str,
        event_key: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        request_callback: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        callback_status = "queued" if request_callback else "not_requested"
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO async_task_events (
                  task_id, event_key, event_type, payload_json, callback_status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, event_key, event_type, json.dumps(payload), callback_status),
            )
            row = conn.execute(
                "SELECT * FROM async_task_events WHERE task_id = ? AND event_key = ?",
                (task_id, event_key),
            ).fetchone()
            if request_callback and row is not None:
                task = conn.execute(
                    "SELECT source_thread_id FROM async_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO async_task_inbox (
                      event_id, task_id, source_thread_id, event_type, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        task_id,
                        task[0] if task else None,
                        event_type,
                        json.dumps(payload),
                    ),
                )
        assert row is not None
        return _event_dict(row), cursor.rowcount == 1

    def inbox(
        self,
        *,
        limit: int = 50,
        unread_only: bool = False,
        source_thread_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if unread_only:
            clauses.append("status = 'unread'")
        if source_thread_id:
            clauses.append("source_thread_id = ?")
            params.append(source_thread_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM async_task_inbox{where} ORDER BY id DESC LIMIT ?",
                params,
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            items.append(item)
        return items

    def acknowledge_inbox(self, inbox_id: int) -> bool:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT event_id FROM async_task_inbox WHERE id = ?", (inbox_id,)
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                """
                UPDATE async_task_inbox
                SET status = 'acknowledged', acknowledged_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (inbox_id,),
            )
            conn.execute(
                """
                UPDATE async_task_events
                SET callback_status = 'acknowledged',
                    acknowledged_at = CURRENT_TIMESTAMP,
                    delivered_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND callback_status IN (
                    'queued', 'pending', 'callback_executed', 'failed'
                  )
                """,
                (row["event_id"],),
            )
        return True

    def events(self, task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM async_task_events
                WHERE task_id = ? ORDER BY id DESC LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [_event_dict(row) for row in rows]

    def pending_callbacks(self, task_id: str | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM async_task_events "
            "WHERE callback_status IN ('queued', 'pending', 'failed')"
        )
        params: tuple[Any, ...] = ()
        if task_id:
            query += " AND task_id = ?"
            params = (task_id,)
        query += " ORDER BY id"
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [_event_dict(row) for row in rows]

    def claim_callback(self, event_id: int) -> bool:
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                UPDATE async_task_events
                SET callback_status = 'executing'
                WHERE id = ? AND callback_status IN ('queued', 'pending', 'failed')
                """,
                (event_id,),
            )
        return cursor.rowcount == 1

    def finish_callback(self, event_id: int, outcome: CallbackOutcome) -> None:
        if outcome.status not in {"callback_executed", "acknowledged", "delivered", "failed"}:
            raise ValueError(f"Unsupported callback outcome: {outcome.status}")
        executed = (
            ", executed_at = CURRENT_TIMESTAMP"
            if outcome.status in {"callback_executed", "acknowledged", "delivered"}
            else ""
        )
        acknowledged = (
            ", acknowledged_at = CURRENT_TIMESTAMP, delivered_at = CURRENT_TIMESTAMP"
            if outcome.status in {"acknowledged", "delivered"}
            else ""
        )
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"""
                UPDATE async_task_events
                SET callback_status = ?, callback_attempts = callback_attempts + 1,
                    callback_error = ?{executed}{acknowledged}
                WHERE id = ?
                """,
                (outcome.status, outcome.error, event_id),
            )
            if outcome.status in {"acknowledged", "delivered"}:
                conn.execute(
                    """
                    UPDATE async_task_inbox
                    SET status = 'acknowledged', acknowledged_at = CURRENT_TIMESTAMP
                    WHERE event_id = ?
                    """,
                    (event_id,),
                )


class ClaudeWorkerSession:
    def __init__(self, config: AsyncTaskConfig, store: AsyncTaskStore) -> None:
        self.config = config
        self.store = store
        record = store.get(config.id) or {}
        self.session_id = record.get("worker_session_id") or str(uuid4())
        self.check_number = len(
            [event for event in store.events(config.id) if event["event_type"] == "worker.observation"]
        )

    def check(self, snapshot: str, event_hint: str) -> WorkerObservation:
        self.check_number += 1
        prompt = _worker_prompt(self.config, snapshot, event_hint)
        schema = json.dumps(
            {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["running", "needs_input", "stalled", "failed", "completed"],
                    },
                    "summary": {"type": "string"},
                    "recommended_action": {"type": "string"},
                },
                "required": ["status", "summary", "recommended_action"],
                "additionalProperties": False,
            },
            separators=(",", ":"),
        )
        command = [
            self.config.claude_command,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            schema,
            "--safe-mode",
            "--strict-mcp-config",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
        ]
        if self.check_number == 1:
            command.extend(["--session-id", self.session_id])
        else:
            command.extend(["--resume", self.session_id])
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.extend(["--", prompt])
        completed = subprocess.run(
            command,
            cwd=self.config.repo,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
        raw = completed.stdout.strip()
        usage = extract_token_usage("\n".join([completed.stdout, completed.stderr]))
        if completed.returncode == 0:
            payload = _parse_claude_payload(raw)
            status = str(payload.get("status") or "running").lower()
            summary = str(payload.get("summary") or "Claude worker returned no summary.")
            action = str(payload.get("recommended_action") or "")
        else:
            status = "worker_error"
            summary = _truncate(completed.stderr.strip() or raw or "Claude worker failed", 2000)
            action = "Inspect Claude CLI authentication and runtime logs."
        self.store.update(
            self.config.id,
            worker_session_id=self.session_id,
            last_worker_summary=summary,
        )
        self._record_ledger_call(prompt, status, summary, action, usage, raw, completed.stderr)
        return WorkerObservation(status, summary, action, usage)

    def _record_ledger_call(
        self,
        prompt: str,
        status: str,
        summary: str,
        action: str,
        usage: Any,
        stdout: str,
        stderr: str,
    ) -> None:
        task_dir = _task_dir(self.store.path, self.config.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        output_path = task_dir / f"worker-check-{self.check_number:04d}.json"
        output_path.write_text(stdout or stderr, encoding="utf-8")
        delegated = max(1, len(prompt) // 4)
        returned = max(1, len(summary + action) // 4)
        result = WorkerResult(
            status="success" if status != "worker_error" else "failed",
            summary=summary,
            risks=[action] if status in {"failed", "stalled", "needs_input", "worker_error"} else [],
            raw_output_path=output_path,
            token_usage=usage,
            token_analysis=TokenAnalysis(
                delegated_context_tokens_estimate=delegated,
                returned_result_tokens_estimate=returned,
                estimated_main_tokens_saved=max(0, delegated - returned),
            ),
        )
        task = Task(
            goal=f"Async check: {self.config.goal}",
            repo=self.config.repo,
            parent_task_label=self.config.goal,
            source_thread_id=self.config.source_thread_id,
            source_harness=self.config.source_harness,
        )
        decision = RouteDecision(
            difficulty=Difficulty.SIMPLE,
            risk=Risk.READ_ONLY,
            can_delegate=True,
            backend="claude_cli",
            worker="claude_async_session",
            model=self.config.model or "claude-default",
            reason=f"Periodic check for async task {self.config.id}.",
        )
        MemoryStore(self.store.path).record_subtask(task=task, decision=decision, result=result)


class AsyncTaskRuntime:
    def __init__(self, memory_path: Path, task_id: str) -> None:
        self.store = AsyncTaskStore(memory_path)
        self.task_id = task_id

    def run(self) -> int:
        record = self.store.get(self.task_id)
        if not record:
            raise ValueError(f"Unknown async task: {self.task_id}")
        if not self.store.claim(self.task_id, os.getpid()):
            return 0
        config = AsyncTaskConfig.from_record(record)
        task_dir = _task_dir(self.store.path, config.id)
        task_dir.mkdir(parents=True, exist_ok=True)
        workload_log = task_dir / "workload.log"
        worker = ClaudeWorkerSession(config, self.store) if config.backend == "claude_cli" else None
        process: subprocess.Popen[str] | None = None
        started = time.monotonic()
        try:
            with workload_log.open("a", encoding="utf-8") as output:
                process = subprocess.Popen(
                    config.workload_command,
                    cwd=config.repo,
                    env=os.environ.copy(),
                    text=True,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self.store.update(config.id, workload_pid=process.pid)
                self.store.record_event(
                    config.id,
                    "task.started",
                    "task.started",
                    {"workload_pid": process.pid, "command": config.workload_command},
                )
                last_snapshot_signature = _snapshot_signature(config, workload_log)
                check_interval = config.interval_sec
                next_check = time.monotonic() + config.interval_sec
                while True:
                    current = self.store.get(config.id) or {}
                    terminal = self._terminal_state(config, process, started, current)
                    if terminal:
                        status, event_type, reason = terminal
                        if process.poll() is None:
                            _terminate_process(process)
                        exit_code = process.poll()
                        observation = self._observe(
                            worker,
                            config,
                            workload_log,
                            f"terminal:{event_type}",
                        )
                        summary = observation.summary if observation else reason
                        self.store.update(
                            config.id,
                            status=status,
                            workload_exit_code=exit_code,
                            last_worker_summary=summary,
                        )
                        event, inserted = self.store.record_event(
                            config.id,
                            event_type,
                            event_type,
                            {
                                "status": status,
                                "reason": reason,
                                "summary": summary,
                                "recommended_action": (
                                    observation.recommended_action if observation else ""
                                ),
                                "workload_exit_code": exit_code,
                            },
                            request_callback=_callback_requested(config, event_type),
                        )
                        if inserted and event["callback_status"] == "queued":
                            deliver_callback(self.store, config, event)
                        return 0 if status == "completed" else 1

                    now = time.monotonic()
                    if worker and now >= next_check:
                        signature = _snapshot_signature(config, workload_log)
                        if signature != last_snapshot_signature:
                            observation = self._observe(worker, config, workload_log, "periodic")
                            if observation:
                                self._record_observation(config, observation)
                            last_snapshot_signature = signature
                            check_interval = config.interval_sec
                        else:
                            check_interval = _next_backoff_interval(
                                config.interval_sec, check_interval
                            )
                        next_check = now + check_interval
                    time.sleep(min(0.5, max(0.05, config.interval_sec / 4)))
        except Exception as error:
            if process and process.poll() is None:
                _terminate_process(process)
            self.store.update(config.id, status="failed", last_worker_summary=str(error))
            event, inserted = self.store.record_event(
                config.id,
                "task.failed",
                "task.failed",
                {"status": "failed", "reason": "runtime_error", "summary": str(error)},
                request_callback=_callback_requested(config, "task.failed"),
            )
            if inserted and event["callback_status"] == "queued":
                deliver_callback(self.store, config, event)
            return 1

    def _terminal_state(
        self,
        config: AsyncTaskConfig,
        process: subprocess.Popen[str],
        started: float,
        record: dict[str, Any],
    ) -> tuple[str, str, str] | None:
        if record.get("stop_requested"):
            return "cancelled", "task.cancelled", "Stop requested by user."
        if config.success_file and config.success_file.exists():
            return "completed", "task.completed", f"Success marker found: {config.success_file}"
        if config.failure_file and config.failure_file.exists():
            return "failed", "task.failed", f"Failure marker found: {config.failure_file}"
        return_code = process.poll()
        if return_code is not None:
            if return_code == 0:
                return "completed", "task.completed", "Workload exited successfully."
            return "failed", "task.failed", f"Workload exited with code {return_code}."
        if config.max_runtime_sec and time.monotonic() - started >= config.max_runtime_sec:
            return "timed_out", "task.timed_out", "Maximum runtime exceeded."
        return None

    def _observe(
        self,
        worker: ClaudeWorkerSession | None,
        config: AsyncTaskConfig,
        workload_log: Path,
        event_hint: str,
    ) -> WorkerObservation | None:
        if not worker:
            return None
        snapshot = build_snapshot(config, workload_log)
        try:
            return worker.check(snapshot, event_hint)
        except Exception as error:
            return WorkerObservation(
                "worker_error",
                f"Claude worker check failed: {error}",
                "The deterministic runtime is still monitoring the workload.",
            )

    def _record_observation(
        self, config: AsyncTaskConfig, observation: WorkerObservation
    ) -> None:
        digest = hashlib.sha1(
            f"{observation.status}\0{observation.summary}".encode("utf-8")
        ).hexdigest()[:12]
        event_type = "worker.observation"
        request_callback = False
        if observation.status == "needs_input":
            event_type = "worker.needs_input"
            request_callback = True
        elif observation.status == "stalled":
            event_type = "worker.stalled"
            request_callback = True
        elif observation.status == "failed":
            event_type = "worker.reported_failure"
            request_callback = True
        event_key = event_type if request_callback else f"observation:{digest}:{uuid4().hex}"
        event, inserted = self.store.record_event(
            config.id,
            event_key,
            event_type,
            {
                "worker_status": observation.status,
                "summary": observation.summary,
                "recommended_action": observation.recommended_action,
            },
            request_callback=request_callback and _callback_requested(config, event_type),
        )
        if inserted and event["callback_status"] == "queued":
            deliver_callback(self.store, config, event)


def build_snapshot(config: AsyncTaskConfig, workload_log: Path) -> str:
    paths = [workload_log, *config.log_paths]
    sections = []
    for path in dict.fromkeys(paths):
        sections.append(f"## {path}\n{_tail_file(path)}")
    return "\n\n".join(sections)


def _snapshot_signature(config: AsyncTaskConfig, workload_log: Path) -> tuple[Any, ...]:
    """Return a cheap deterministic signature without reading file contents."""

    signature: list[Any] = []
    for path in dict.fromkeys([workload_log, *config.log_paths]):
        try:
            stat = path.stat()
            signature.append((str(path), True, stat.st_size, stat.st_mtime_ns))
        except OSError:
            signature.append((str(path), False, 0, 0))
    return tuple(signature)


def _next_backoff_interval(base: float, current: float) -> float:
    """Exponentially back off unchanged snapshots, capped at five minutes."""

    return min(max(base, current * 2), max(base, min(300.0, base * 16)))


class CodexExecNotifier:
    """Compatibility notifier; successful execution is not a UI acknowledgement."""

    def notify(
        self, config: AsyncTaskConfig, event: dict[str, Any], message: str
    ) -> CallbackOutcome:
        completed = subprocess.run(
            [
                config.codex_command,
                "exec",
                "resume",
                "-c",
                'sandbox_mode="read-only"',
                "-c",
                'approval_policy="never"',
                config.source_thread_id or "",
                message,
            ],
            cwd=config.repo,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=1800,
            check=False,
        )
        if completed.returncode == 0:
            return CallbackOutcome("callback_executed", output=completed.stdout)
        return CallbackOutcome(
            "failed",
            error=_truncate(completed.stdout, 2000),
            output=completed.stdout,
        )


def deliver_callback(
    store: AsyncTaskStore,
    config: AsyncTaskConfig,
    event: dict[str, Any],
    notifier: CallbackNotifier | None = None,
) -> bool:
    if config.callback_mode != "codex_resume" or not config.source_thread_id:
        return False
    if not store.claim_callback(event["id"]):
        return False
    payload = event["payload"]
    message = "\n".join(
        [
            f"Cost Router async task `{config.id}` emitted `{event['event_type']}`.",
            f"Goal: {config.goal}",
            f"Status: {payload.get('status') or payload.get('worker_status') or 'unknown'}",
            f"Summary: {payload.get('summary') or payload.get('reason') or 'No summary'}",
            f"Recommended action: {payload.get('recommended_action') or 'Review the event and respond.'}",
            f"Repository: {config.repo}",
            "This is a compatibility notification, not proof that a visible UI received it.",
            "Do not modify files or run commands. Briefly acknowledge the event only.",
        ]
    )
    task_dir = _task_dir(store.path, config.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    callback_log = task_dir / f"callback-{event['id']}.log"
    try:
        outcome = (notifier or CodexExecNotifier()).notify(config, event, message)
        callback_log.write_text(outcome.output or outcome.error or "", encoding="utf-8")
    except Exception as exc:
        outcome = CallbackOutcome("failed", error=str(exc), output=str(exc))
        callback_log.write_text(outcome.output, encoding="utf-8")
    store.finish_callback(event["id"], outcome)
    return outcome.status in {"callback_executed", "acknowledged", "delivered"}


def retry_callbacks(memory_path: Path, task_id: str | None = None) -> tuple[int, int]:
    store = AsyncTaskStore(memory_path)
    attempted = executed = 0
    for event in store.pending_callbacks(task_id):
        record = store.get(event["task_id"])
        if not record:
            continue
        config = AsyncTaskConfig.from_record(record)
        if config.callback_mode != "codex_resume":
            continue
        attempted += 1
        executed += int(deliver_callback(store, config, event))
    return attempted, executed


def _callback_requested(config: AsyncTaskConfig, event_type: str) -> bool:
    return (
        config.callback_mode in {"inbox", "codex_resume"}
        and event_type in CALLBACK_EVENT_TYPES
    )


def _worker_prompt(config: AsyncTaskConfig, snapshot: str, event_hint: str) -> str:
    return f"""You are the persistent worker for an asynchronous software task.
Transfer authorization: external_policy={config.external_policy}, data_classification={config.data_classification}.
Assess only the supplied runtime snapshot. Do not claim to have read other files or run commands.
Return the requested structured object. Use `needs_input` only when human or orchestrator input is
actually required, and `stalled` only when the evidence shows progress has stopped. Runtime process
exit and marker files are decided by the deterministic runtime process, not by you.
An empty or not-yet-created log near startup is normal and must remain `running` unless other evidence
shows a problem.

Task ID: {config.id}
Goal: {config.goal}
Runtime event: {event_hint}

Snapshot:
{snapshot}
"""


def _parse_claude_payload(raw: str) -> dict[str, Any]:
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "running", "summary": _truncate(raw, 2000)}
    if isinstance(outer, dict):
        structured = outer.get("structured_output")
        if isinstance(structured, dict):
            return structured
        result = outer.get("result")
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                return {"status": "running", "summary": _truncate(result, 2000)}
            if isinstance(parsed, dict):
                return parsed
        if "status" in outer:
            return outer
    return {"status": "running", "summary": _truncate(raw, 2000)}


def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json"))
    return item


def _task_dir(memory_path: Path, task_id: str) -> Path:
    return memory_path.parent / "async-tasks" / task_id


def _tail_file(path: Path, max_bytes: int = 16_000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except OSError as error:
        return f"<unavailable: {error}>"
    return data.decode("utf-8", errors="replace")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def runtime_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cost-router-async-runtime")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--memory", required=True)
    args = parser.parse_args(argv)
    return AsyncTaskRuntime(Path(args.memory).expanduser().resolve(), args.task_id).run()


if __name__ == "__main__":
    raise SystemExit(runtime_main())
