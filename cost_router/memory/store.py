from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core.contracts import RouteDecision, Task, VerificationResult, WorkerResult

if TYPE_CHECKING:
    from ..core.graph import DecompositionPlan


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  goal TEXT NOT NULL,
  repo TEXT NOT NULL,
  parent_task_label TEXT,
  source_thread_id TEXT,
  source_harness TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subtasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  backend TEXT NOT NULL,
  worker TEXT NOT NULL,
  model TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  result_json TEXT,
  verification_json TEXT,
  executed INTEGER NOT NULL DEFAULT 0,
  status TEXT,
  accepted INTEGER,
  mode TEXT NOT NULL DEFAULT 'read_only',
  input_tokens INTEGER,
  output_tokens INTEGER,
  total_tokens INTEGER,
  delegated_context_tokens_estimate INTEGER,
  returned_result_tokens_estimate INTEGER,
  estimated_main_tokens_saved INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  fact TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'verified',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  body_path TEXT,
  visibility TEXT NOT NULL DEFAULT 'orchestrator',
  status TEXT NOT NULL DEFAULT 'active',
  owner TEXT,
  metadata_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  src_node_id TEXT NOT NULL,
  dst_node_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  metadata_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id),
  FOREIGN KEY(src_node_id) REFERENCES nodes(id),
  FOREIGN KEY(dst_node_id) REFERENCES nodes(id)
);

CREATE TABLE IF NOT EXISTS worker_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  worker_node_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  verifier_status TEXT NOT NULL DEFAULT 'unverified',
  committed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id),
  FOREIGN KEY(worker_node_id) REFERENCES nodes(id)
);

CREATE TABLE IF NOT EXISTS file_locks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  artifact_node_id TEXT NOT NULL,
  worker_node_id TEXT NOT NULL,
  lock_type TEXT NOT NULL,
  base_hash TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  expires_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES runs(id),
  FOREIGN KEY(artifact_node_id) REFERENCES nodes(id),
  FOREIGN KEY(worker_node_id) REFERENCES nodes(id)
);

CREATE TABLE IF NOT EXISTS async_tasks (
  id TEXT PRIMARY KEY,
  goal TEXT NOT NULL,
  repo TEXT NOT NULL,
  backend TEXT NOT NULL,
  model TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  workload_command_json TEXT NOT NULL,
  log_paths_json TEXT NOT NULL DEFAULT '[]',
  interval_sec REAL NOT NULL DEFAULT 60,
  max_runtime_sec INTEGER,
  success_file TEXT,
  failure_file TEXT,
  source_thread_id TEXT,
  source_harness TEXT NOT NULL DEFAULT 'cli',
  callback_mode TEXT NOT NULL DEFAULT 'none',
  claude_command TEXT NOT NULL DEFAULT 'claude',
  codex_command TEXT NOT NULL DEFAULT 'codex',
  external_policy TEXT NOT NULL DEFAULT 'ask',
  data_classification TEXT NOT NULL DEFAULT 'private',
  worker_session_id TEXT,
  runtime_pid INTEGER,
  workload_pid INTEGER,
  workload_exit_code INTEGER,
  last_worker_summary TEXT,
  stop_requested INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS async_task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  event_key TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  callback_status TEXT NOT NULL DEFAULT 'not_requested',
  callback_attempts INTEGER NOT NULL DEFAULT 0,
  callback_error TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  delivered_at TEXT,
  UNIQUE(task_id, event_key),
  FOREIGN KEY(task_id) REFERENCES async_tasks(id)
);
"""


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)
            _migrate_schema(conn)

    def record_run(self, task: Task) -> None:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO runs (
                  id, goal, repo, parent_task_label, source_thread_id, source_harness
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  parent_task_label = COALESCE(runs.parent_task_label, excluded.parent_task_label),
                  source_thread_id = COALESCE(runs.source_thread_id, excluded.source_thread_id),
                  source_harness = COALESCE(runs.source_harness, excluded.source_harness)
                """,
                (
                    task.id,
                    task.goal,
                    str(task.repo),
                    task.parent_task_label,
                    task.source_thread_id,
                    task.source_harness,
                ),
            )

    def record_subtask(
        self,
        *,
        task: Task,
        decision: RouteDecision,
        result: WorkerResult | None = None,
        verification: VerificationResult | None = None,
    ) -> None:
        self.record_run(task)
        usage = result.token_usage if result else None
        analysis = result.token_analysis if result else None
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO subtasks (
                  run_id, backend, worker, model, decision_json, result_json,
                  verification_json, executed, status, accepted, mode,
                  input_tokens, output_tokens, total_tokens,
                  delegated_context_tokens_estimate, returned_result_tokens_estimate,
                  estimated_main_tokens_saved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    decision.backend,
                    decision.worker,
                    decision.model,
                    _dump(decision.to_dict()),
                    _dump(result.to_dict()) if result else None,
                    _dump(verification.to_dict()) if verification else None,
                    1 if result else 0,
                    result.status if result else "pending",
                    1 if verification and verification.accepted else 0 if verification else None,
                    task.constraints.mode.value,
                    usage.input_tokens if usage else None,
                    usage.output_tokens if usage else None,
                    usage.total_tokens if usage else None,
                    analysis.delegated_context_tokens_estimate if analysis else None,
                    analysis.returned_result_tokens_estimate if analysis else None,
                    analysis.estimated_main_tokens_saved if analysis else None,
                ),
            )
            subtask_id = int(cursor.lastrowid)
            worker_node_id = self._record_worker_graph(
                conn=conn,
                task=task,
                subtask_id=subtask_id,
                decision=decision,
                result=result,
                verification=verification,
            )
            if verification:
                for fact in verification.memory_facts:
                    conn.execute(
                        "INSERT INTO facts (run_id, fact, status) VALUES (?, ?, 'verified')",
                        (task.id, fact),
                    )
                    conn.execute(
                        """
                        INSERT INTO worker_events (
                          run_id, worker_node_id, event_type, payload_json, verifier_status, committed
                        ) VALUES (?, ?, 'proposed_fact', ?, 'verified', 1)
                        """,
                        (
                            task.id,
                            worker_node_id,
                            _dump({"fact": fact, "source": "verifier.memory_facts"}),
                        ),
                    )

    def record_decomposition(self, task: Task, plan: DecompositionPlan) -> None:
        """Persist a validated contract graph before worker execution begins."""
        plan.validate()
        if plan.situation.task_id != task.id:
            raise ValueError("Decomposition plan and task ids must match.")
        self.record_run(task)
        root_node_id = f"{task.id}:root_contract"
        node_ids = {
            node_id: f"{task.id}:contract:{node_id}" for node_id in plan.graph.nodes
        }
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (
                  id, run_id, kind, title, summary, visibility, status,
                  owner, metadata_json, updated_at
                ) VALUES (?, ?, 'root_contract', ?, ?, 'orchestrator', 'active',
                          'orchestrator', ?, CURRENT_TIMESTAMP)
                """,
                (
                    root_node_id,
                    task.id,
                    task.parent_task_label or task.goal,
                    plan.situation.objective,
                    _dump(
                        {
                            "shape": plan.shape.value,
                            "reasons": plan.reasons,
                            "situation": plan.situation.to_dict(),
                            "root_contract": plan.situation.root_contract.to_dict(),
                        }
                    ),
                ),
            )
            for node_id, node in plan.graph.nodes.items():
                stored_node_id = node_ids[node_id]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes (
                      id, run_id, kind, title, summary, visibility, status,
                      owner, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'worker', 'planned', ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        stored_node_id,
                        task.id,
                        node.kind.value,
                        node.objective,
                        node.verification.root_contribution,
                        node.assigned_worker_id,
                        _dump(node.to_dict()),
                    ),
                )
                self._insert_edge(
                    conn,
                    run_id=task.id,
                    src=root_node_id,
                    dst=stored_node_id,
                    edge_type="contains",
                    metadata={"graph_version": plan.graph.version},
                )
            for edge in plan.graph.edges:
                self._insert_edge(
                    conn,
                    run_id=task.id,
                    src=node_ids[edge.source],
                    dst=node_ids[edge.target],
                    edge_type=edge.edge_type,
                    metadata={"graph_version": plan.graph.version},
                )

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  runs.id,
                  runs.goal,
                  runs.repo,
                  runs.parent_task_label,
                  runs.source_thread_id,
                  runs.source_harness,
                  runs.created_at,
                  COUNT(subtasks.id) AS subtask_count
                FROM runs
                LEFT JOIN subtasks ON subtasks.run_id = runs.id
                GROUP BY runs.id
                ORDER BY runs.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_subtasks(self, limit: int = 10) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  id,
                  run_id,
                  backend,
                  worker,
                  model,
                  executed,
                  status,
                  accepted,
                  mode,
                  input_tokens,
                  output_tokens,
                  total_tokens,
                  delegated_context_tokens_estimate,
                  returned_result_tokens_estimate,
                  estimated_main_tokens_saved,
                  result_json,
                  verification_json,
                  created_at
                FROM subtasks
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        subtasks = []
        for row in rows:
            item = dict(row)
            verification = json.loads(item["verification_json"]) if item["verification_json"] else None
            result = json.loads(item["result_json"]) if item.get("result_json") else None
            item["token_usage"] = result.get("token_usage") if result else None
            item["token_analysis"] = result.get("token_analysis") if result else None
            item.pop("verification_json", None)
            item.pop("result_json", None)
            item["executed"] = bool(item["executed"])
            subtasks.append(item)
        return subtasks

    def recent_facts(self, limit: int = 10) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, run_id, fact, status, created_at
                FROM facts
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_graph_nodes(self, limit: int = 20) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, run_id, kind, title, summary, body_path, visibility, status,
                       owner, metadata_json, created_at, updated_at
                FROM nodes
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        nodes = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata_json"]) if item["metadata_json"] else {}
            item.pop("metadata_json", None)
            nodes.append(item)
        return nodes

    def recent_graph_edges(self, limit: int = 30) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, run_id, src_node_id, dst_node_id, edge_type, metadata_json, created_at
                FROM edges
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        edges = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata_json"]) if item["metadata_json"] else {}
            item.pop("metadata_json", None)
            edges.append(item)
        return edges

    def recent_worker_events(self, limit: int = 30) -> list[dict[str, Any]]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, run_id, worker_node_id, event_type, payload_json,
                       verifier_status, committed, created_at
                FROM worker_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload_json"]) if item["payload_json"] else {}
            item.pop("payload_json", None)
            item["committed"] = bool(item["committed"])
            events.append(item)
        return events

    def graph_summary(self) -> dict[str, int]:
        self.init()
        with sqlite3.connect(self.path) as conn:
            kinds = conn.execute(
                "SELECT kind, COUNT(*) FROM nodes GROUP BY kind"
            ).fetchall()
            edges = conn.execute(
                "SELECT edge_type, COUNT(*) FROM edges GROUP BY edge_type"
            ).fetchall()
            event_count = conn.execute("SELECT COUNT(*) FROM worker_events").fetchone()[0]
            lock_count = conn.execute("SELECT COUNT(*) FROM file_locks").fetchone()[0]
        summary = {
            "nodes": sum(count for _, count in kinds),
            "edges": sum(count for _, count in edges),
            "worker_events": int(event_count),
            "file_locks": int(lock_count),
        }
        for kind, count in kinds:
            summary[f"nodes_{kind}"] = int(count)
        for edge_type, count in edges:
            summary[f"edges_{edge_type}"] = int(count)
        return summary

    def token_summary(self) -> dict[str, int]:
        self.init()
        summary = {
            "subtasks_with_results": 0,
            "actual_worker_tokens": 0,
            "delegated_context_tokens_estimate": 0,
            "returned_result_tokens_estimate": 0,
            "estimated_main_tokens_saved": 0,
        }
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT total_tokens, delegated_context_tokens_estimate,
                       returned_result_tokens_estimate, estimated_main_tokens_saved
                FROM subtasks
                WHERE executed = 1
                """
            ).fetchall()
        for total, delegated, returned, saved in rows:
            summary["subtasks_with_results"] += 1
            summary["actual_worker_tokens"] += int(total or 0)
            summary["delegated_context_tokens_estimate"] += int(delegated or 0)
            summary["returned_result_tokens_estimate"] += int(returned or 0)
            summary["estimated_main_tokens_saved"] += int(saved or 0)
        return summary

    def _record_worker_graph(
        self,
        *,
        conn: sqlite3.Connection,
        task: Task,
        subtask_id: int,
        decision: RouteDecision,
        result: WorkerResult | None,
        verification: VerificationResult | None,
    ) -> str:
        control_node_id = f"{task.id}:control"
        worker_node_id = f"{task.id}:worker:{subtask_id}"
        status = "verified" if verification and verification.accepted else "done" if result else "pending"
        owner = f"{decision.backend}:{decision.worker}"
        conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
              id, run_id, kind, title, summary, visibility, status, owner, metadata_json, updated_at
            ) VALUES (?, ?, 'control', ?, ?, 'orchestrator', 'active', 'orchestrator', ?, CURRENT_TIMESTAMP)
            """,
            (
                control_node_id,
                task.id,
                "Private orchestrator state",
                task.goal,
                _dump(
                    {
                        "note": "This is a lightweight control node. Private reasoning and hooks are not stored here.",
                        "repo": str(task.repo),
                    }
                ),
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
              id, run_id, kind, title, summary, visibility, status, owner, metadata_json, updated_at
            ) VALUES (?, ?, 'worker_task', ?, ?, 'worker', ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                worker_node_id,
                task.id,
                task.goal,
                result.summary if result else decision.reason,
                status,
                owner,
                _dump(
                    {
                        "subtask_id": subtask_id,
                        "decision": decision.to_dict(),
                        "constraints": task.constraints.to_dict(),
                    }
                ),
            ),
        )
        self._insert_edge(
            conn,
            run_id=task.id,
            src=control_node_id,
            dst=worker_node_id,
            edge_type="delegates_to",
            metadata={"source": "orchestrator.dispatch"},
        )

        write_paths = {path.resolve() for path in task.write_paths}
        graph_paths = list(dict.fromkeys([*task.paths, *task.write_paths]))
        for path in graph_paths:
            artifact_node_id = self._artifact_node_id(task.id, path)
            stat = _path_stat(path)
            writable = path.resolve() in write_paths
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (
                  id, run_id, kind, title, summary, body_path, visibility, status,
                  owner, metadata_json, updated_at
                ) VALUES (?, ?, 'artifact', ?, ?, ?, 'worker', 'active', NULL, ?, CURRENT_TIMESTAMP)
                """,
                (
                    artifact_node_id,
                    task.id,
                    path.name or str(path),
                    f"Allowed {'write' if writable else 'read'} path: {path}",
                    str(path),
                    _dump(
                        {
                            "artifact_type": "write_path" if writable else "task_path",
                            "path": str(path),
                            **stat,
                        }
                    ),
                ),
            )
            self._insert_edge(
                conn,
                run_id=task.id,
                src=worker_node_id,
                dst=artifact_node_id,
                edge_type="may_write" if writable else "may_read",
                metadata={"source": "task.write_paths" if writable else "task.paths"},
            )
            conn.execute(
                """
                INSERT INTO file_locks (
                  run_id, artifact_node_id, worker_node_id, lock_type, base_hash, status
                ) VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (
                    task.id,
                    artifact_node_id,
                    worker_node_id,
                    "patch" if writable else "read",
                    stat.get("sha256"),
                ),
            )

        for path in task.context_packs:
            context_node_id = self._context_pack_node_id(task.id, path)
            stat = _path_stat(path)
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (
                  id, run_id, kind, title, summary, body_path, visibility, status,
                  owner, metadata_json, updated_at
                ) VALUES (?, ?, 'context_pack', ?, ?, ?, 'worker', 'active', 'orchestrator', ?, CURRENT_TIMESTAMP)
                """,
                (
                    context_node_id,
                    task.id,
                    path.name or str(path),
                    f"Worker-readable context pack: {path}",
                    str(path),
                    _dump(
                        {
                            "context_type": "file",
                            "path": str(path),
                            **stat,
                        }
                    ),
                ),
            )
            self._insert_edge(
                conn,
                run_id=task.id,
                src=worker_node_id,
                dst=context_node_id,
                edge_type="uses_context",
                metadata={"source": "task.context_packs"},
            )

        if result:
            if result.proposed_patch_path:
                patch_node_id = self._artifact_node_id(task.id, result.proposed_patch_path)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes (
                      id, run_id, kind, title, summary, body_path, visibility, status,
                      owner, metadata_json, updated_at
                    ) VALUES (?, ?, 'artifact', ?, ?, ?, 'orchestrator', 'proposed', ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        patch_node_id,
                        task.id,
                        result.proposed_patch_path.name,
                        "Worker patch proposal",
                        str(result.proposed_patch_path),
                        owner,
                        _dump(
                            {
                                "artifact_type": "patch_proposal",
                                "changed_paths": result.changed_paths,
                                **_path_stat(result.proposed_patch_path),
                            }
                        ),
                    ),
                )
                self._insert_edge(
                    conn,
                    run_id=task.id,
                    src=worker_node_id,
                    dst=patch_node_id,
                    edge_type="proposes_patch",
                    metadata={"changed_paths": result.changed_paths},
                )
            if result.raw_output_path:
                output_node_id = self._artifact_node_id(task.id, result.raw_output_path)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes (
                      id, run_id, kind, title, summary, body_path, visibility, status,
                      owner, metadata_json, updated_at
                    ) VALUES (?, ?, 'artifact', ?, ?, ?, 'orchestrator', 'active', ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        output_node_id,
                        task.id,
                        result.raw_output_path.name,
                        "Worker raw output",
                        str(result.raw_output_path),
                        owner,
                        _dump({"artifact_type": "worker_output", **_path_stat(result.raw_output_path)}),
                    ),
                )
                self._insert_edge(
                    conn,
                    run_id=task.id,
                    src=worker_node_id,
                    dst=output_node_id,
                    edge_type="evidence_for",
                    metadata={"source": "worker.raw_output_path"},
                )

            conn.execute(
                """
                INSERT INTO worker_events (
                  run_id, worker_node_id, event_type, payload_json, verifier_status, committed
                ) VALUES (?, ?, 'final', ?, ?, ?)
                """,
                (
                    task.id,
                    worker_node_id,
                    _dump(result.to_dict()),
                    "verified" if verification and verification.accepted else "rejected"
                    if verification
                    else "unverified",
                    1 if verification and verification.accepted else 0,
                ),
            )
            if result.status != "success":
                conn.execute(
                    """
                    INSERT INTO worker_events (
                      run_id, worker_node_id, event_type, payload_json, verifier_status, committed
                    ) VALUES (?, ?, 'error', ?, 'unverified', 0)
                    """,
                    (
                        task.id,
                        worker_node_id,
                        _dump({"summary": result.summary, "risks": result.risks}),
                    ),
                )

        if verification:
            self._insert_edge(
                conn,
                run_id=task.id,
                src=worker_node_id,
                dst=worker_node_id,
                edge_type="verified_as",
                metadata=verification.to_dict(),
            )

        return worker_node_id

    def _artifact_node_id(self, run_id: str, path: Path) -> str:
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        return f"{run_id}:artifact:{digest}"

    def _context_pack_node_id(self, run_id: str, path: Path) -> str:
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        return f"{run_id}:context:{digest}"

    def _insert_edge(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        src: str,
        dst: str,
        edge_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO edges (run_id, src_node_id, dst_node_id, edge_type, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, src, dst, edge_type, _dump(metadata or {})),
        )


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _path_stat(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"exists": False}
    data: dict[str, Any] = {
        "exists": True,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "byte_size": stat.st_size,
        "mtime": stat.st_mtime,
    }
    if path.is_file() and stat.st_size <= 5_000_000:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = None
        data["sha256"] = digest
    return data


def _migrate_schema(conn: sqlite3.Connection) -> None:
    run_columns = {
        "parent_task_label": "TEXT",
        "source_thread_id": "TEXT",
        "source_harness": "TEXT",
    }
    subtask_columns = {
        "executed": "INTEGER NOT NULL DEFAULT 0",
        "status": "TEXT",
        "accepted": "INTEGER",
        "mode": "TEXT NOT NULL DEFAULT 'read_only'",
        "input_tokens": "INTEGER",
        "output_tokens": "INTEGER",
        "total_tokens": "INTEGER",
        "delegated_context_tokens_estimate": "INTEGER",
        "returned_result_tokens_estimate": "INTEGER",
        "estimated_main_tokens_saved": "INTEGER",
    }
    _add_missing_columns(conn, "runs", run_columns)
    _add_missing_columns(conn, "subtasks", subtask_columns)
    _add_missing_columns(
        conn,
        "async_tasks",
        {
            "external_policy": "TEXT NOT NULL DEFAULT 'ask'",
            "data_classification": "TEXT NOT NULL DEFAULT 'private'",
        },
    )
    _backfill_subtasks(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_created_at ON subtasks(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_backend ON subtasks(backend)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_run_id ON subtasks(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_thread ON runs(source_thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_async_tasks_status ON async_tasks(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_async_task_events_task ON async_task_events(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_async_task_events_callback "
        "ON async_task_events(callback_status)"
    )


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, declaration in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def _backfill_subtasks(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, decision_json, result_json, verification_json
        FROM subtasks
        WHERE result_json IS NOT NULL AND (
          executed = 0 OR status IS NULL OR
          delegated_context_tokens_estimate IS NULL OR
          returned_result_tokens_estimate IS NULL OR
          estimated_main_tokens_saved IS NULL
        )
        """
    ).fetchall()
    for subtask_id, raw_decision, raw_result, raw_verification in rows:
        decision = _load_json(raw_decision)
        result = _load_json(raw_result)
        verification = _load_json(raw_verification)
        usage = result.get("token_usage") or {}
        analysis = result.get("token_analysis") or {}
        risk = decision.get("risk")
        conn.execute(
            """
            UPDATE subtasks SET
              executed = 1,
              status = COALESCE(status, ?),
              accepted = COALESCE(accepted, ?),
              mode = CASE WHEN ? = 'patch' THEN 'patch' ELSE mode END,
              input_tokens = COALESCE(input_tokens, ?),
              output_tokens = COALESCE(output_tokens, ?),
              total_tokens = COALESCE(total_tokens, ?),
              delegated_context_tokens_estimate = COALESCE(delegated_context_tokens_estimate, ?),
              returned_result_tokens_estimate = COALESCE(returned_result_tokens_estimate, ?),
              estimated_main_tokens_saved = COALESCE(estimated_main_tokens_saved, ?)
            WHERE id = ?
            """,
            (
                result.get("status") or "unknown",
                1 if verification.get("accepted") is True else 0
                if verification
                else None,
                risk,
                usage.get("input_tokens"),
                usage.get("output_tokens"),
                usage.get("total_tokens"),
                analysis.get("delegated_context_tokens_estimate"),
                analysis.get("returned_result_tokens_estimate"),
                analysis.get("estimated_main_tokens_saved"),
                subtask_id,
            ),
        )


def _load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}
