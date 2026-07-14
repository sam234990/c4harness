"""SQLite execution-history repository, separate from shared task memory."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import ExecutionOutcome, FailureAttribution, OutcomeStatus, PlanSnapshot


HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS history_plans (
  task_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  PRIMARY KEY(task_id, version)
);
CREATE TABLE IF NOT EXISTS history_outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  worker_arm_id TEXT,
  status TEXT NOT NULL,
  capability_dimensions_json TEXT NOT NULL,
  verification_status TEXT,
  failure_attribution TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  total_tokens INTEGER,
  latency_ms INTEGER,
  artifact_refs_json TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
"""


class SQLiteHistoryRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(HISTORY_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def append_plan(self, snapshot: PlanSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO history_plans VALUES (?, ?, ?, ?)",
                (snapshot.task_id, snapshot.version, json.dumps(snapshot.payload), snapshot.recorded_at),
            )

    def append_outcome(self, outcome: ExecutionOutcome) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO history_outcomes (
                task_id,node_id,worker_arm_id,status,capability_dimensions_json,
                verification_status,failure_attribution,input_tokens,output_tokens,
                total_tokens,latency_ms,artifact_refs_json,recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    outcome.task_id, outcome.node_id, outcome.worker_arm_id,
                    outcome.status.value, json.dumps(outcome.capability_dimensions),
                    outcome.verification_status, outcome.failure_attribution.value,
                    outcome.input_tokens, outcome.output_tokens, outcome.total_tokens,
                    outcome.latency_ms, json.dumps(outcome.artifact_refs), outcome.recorded_at,
                ),
            )

    def outcomes_for_worker(self, worker_arm_id: str) -> list[ExecutionOutcome]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM history_outcomes WHERE worker_arm_id=? ORDER BY id",
                (worker_arm_id,),
            ).fetchall()
        return [
            ExecutionOutcome(
                task_id=row["task_id"], node_id=row["node_id"],
                worker_arm_id=row["worker_arm_id"], status=OutcomeStatus(row["status"]),
                capability_dimensions=tuple(json.loads(row["capability_dimensions_json"])),
                verification_status=row["verification_status"],
                failure_attribution=FailureAttribution(row["failure_attribution"]),
                input_tokens=row["input_tokens"], output_tokens=row["output_tokens"],
                total_tokens=row["total_tokens"], latency_ms=row["latency_ms"],
                artifact_refs=tuple(json.loads(row["artifact_refs_json"])),
                recorded_at=row["recorded_at"],
            )
            for row in rows
        ]
