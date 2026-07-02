from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .memory import MemoryStore


KNOWN_BACKENDS = ("claude_cli", "codex_subagent", "opencode")


class AnalyticsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def metadata(self) -> dict[str, Any]:
        MemoryStore(self.path).init()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), MAX(created_at) FROM subtasks WHERE executed = 1"
            ).fetchone()
            backends = [
                item[0]
                for item in conn.execute(
                    "SELECT DISTINCT backend FROM subtasks WHERE backend <> '' ORDER BY backend"
                )
            ]
        return {
            "memory_path": str(self.path.resolve()),
            "database_exists": self.path.exists(),
            "executed_calls": int(row[0]),
            "last_call_at": _utc_iso(row[1]) if row[1] else None,
            "backends": list(dict.fromkeys([*KNOWN_BACKENDS, *backends])),
        }

    def overview(self, range_name: str, timezone: str) -> dict[str, Any]:
        rows = self._metric_rows(range_name)
        known = list(KNOWN_BACKENDS)
        known.extend(row["backend"] for row in rows)
        providers: dict[str, dict[str, Any]] = {
            backend: _empty_metrics() for backend in dict.fromkeys(known)
        }
        total = _empty_metrics()
        for row in rows:
            _add_metrics(total, row)
            _add_metrics(providers[row["backend"]], row)
        return {
            "range": range_name,
            "timezone": _timezone(timezone).key,
            "totals": total,
            "providers": [
                {"backend": backend, **metrics} for backend, metrics in providers.items()
            ],
        }

    def timeseries(
        self, range_name: str, bucket: str, metric: str, timezone: str
    ) -> dict[str, Any]:
        tz = _timezone(timezone)
        rows = self._metric_rows(range_name)
        bucket = "month" if bucket == "month" else "day"
        allowed_metrics = {
            "delegated_tokens": "delegated_context_tokens_estimate",
            "saved_tokens": "estimated_main_tokens_saved",
            "worker_tokens": "total_tokens",
            "calls": None,
        }
        metric_column = allowed_metrics.get(metric, allowed_metrics["delegated_tokens"])
        metric = metric if metric in allowed_metrics else "delegated_tokens"
        discovered = list(dict.fromkeys([*KNOWN_BACKENDS, *[row["backend"] for row in rows]]))
        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            local = _parse_utc(row["created_at"]).astimezone(tz)
            key = local.strftime("%Y-%m" if bucket == "month" else "%Y-%m-%d")
            grouped.setdefault(key, {})
            value = 1 if metric_column is None else int(row[metric_column] or 0)
            grouped[key][row["backend"]] = grouped[key].get(row["backend"], 0) + value

        keys = _bucket_keys(range_name, bucket, tz, rows)
        points = [
            {
                "bucket": key,
                "values": {backend: grouped.get(key, {}).get(backend, 0) for backend in discovered},
            }
            for key in keys
        ]
        return {
            "range": range_name,
            "bucket": bucket,
            "metric": metric,
            "timezone": tz.key,
            "backends": discovered,
            "points": points,
        }

    def calls(
        self,
        *,
        range_name: str,
        backend: str = "",
        model: str = "",
        status: str = "",
        project: str = "",
        query: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        clauses = ["s.executed = 1"]
        params: list[Any] = []
        _append_range(clauses, params, range_name)
        if backend:
            clauses.append("s.backend = ?")
            params.append(backend)
        if model:
            clauses.append("s.model = ?")
            params.append(model)
        if status:
            if status == "accepted":
                clauses.append("s.accepted = 1")
            elif status == "rejected":
                clauses.append("s.accepted = 0")
            elif status == "error":
                clauses.append("s.status <> 'success'")
        if project:
            clauses.append("r.repo LIKE ?")
            params.append(f"%{project}%")
        if query:
            clauses.append(
                "(r.goal LIKE ? OR COALESCE(r.parent_task_label, '') LIKE ? "
                "OR COALESCE(r.source_thread_id, '') LIKE ?)"
            )
            params.extend([f"%{query}%"] * 3)
        where = " AND ".join(clauses)
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM subtasks s JOIN runs r ON r.id=s.run_id WHERE {where}",
                    params,
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT s.id, s.run_id, s.backend, s.worker, s.model, s.status, s.accepted,
                       s.mode, s.input_tokens, s.output_tokens, s.total_tokens,
                       s.delegated_context_tokens_estimate,
                       s.returned_result_tokens_estimate, s.estimated_main_tokens_saved,
                       s.created_at, r.goal, r.repo, r.parent_task_label,
                       r.source_thread_id, r.source_harness
                FROM subtasks s JOIN runs r ON r.id=s.run_id
                WHERE {where}
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {
            "items": [_call_row(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def call_detail(self, subtask_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.*, r.goal, r.repo, r.parent_task_label,
                       r.source_thread_id, r.source_harness
                FROM subtasks s JOIN runs r ON r.id=s.run_id
                WHERE s.id = ?
                """,
                (subtask_id,),
            ).fetchone()
        if not row:
            return None
        item = _call_row(dict(row))
        result = _load_json(row["result_json"])
        verification = _load_json(row["verification_json"])
        decision = _load_json(row["decision_json"])
        item.update(
            {
                "route_reason": decision.get("reason"),
                "difficulty": decision.get("difficulty"),
                "risk": decision.get("risk"),
                "summary": result.get("summary"),
                "evidence": result.get("evidence") or [],
                "risks": result.get("risks") or [],
                "next_steps": result.get("next_steps") or [],
                "raw_output_path": result.get("raw_output_path"),
                "proposed_patch_path": result.get("proposed_patch_path"),
                "changed_paths": result.get("changed_paths") or [],
                "policy_violations": result.get("policy_violations") or [],
                "verification": verification or None,
            }
        )
        return item

    def filter_options(self) -> dict[str, list[str]]:
        MemoryStore(self.path).init()
        with self._connect() as conn:
            backends = [row[0] for row in conn.execute("SELECT DISTINCT backend FROM subtasks ORDER BY backend")]
            models = [row[0] for row in conn.execute("SELECT DISTINCT model FROM subtasks ORDER BY model")]
            projects = [row[0] for row in conn.execute("SELECT DISTINCT repo FROM runs ORDER BY repo")]
        return {
            "backends": list(dict.fromkeys([*KNOWN_BACKENDS, *backends])),
            "models": models,
            "projects": projects,
        }

    def _metric_rows(self, range_name: str) -> list[sqlite3.Row]:
        clauses = ["executed = 1"]
        params: list[Any] = []
        _append_range(clauses, params, range_name)
        with self._connect() as conn:
            return conn.execute(
                f"""
                SELECT backend, total_tokens, delegated_context_tokens_estimate,
                       returned_result_tokens_estimate, estimated_main_tokens_saved,
                       created_at
                FROM subtasks
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at
                """,
                params,
            ).fetchall()

    def _connect(self) -> sqlite3.Connection:
        MemoryStore(self.path).init()
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn


def _empty_metrics() -> dict[str, int]:
    return {
        "calls": 0,
        "actual_token_calls": 0,
        "worker_tokens": 0,
        "delegated_tokens": 0,
        "returned_tokens": 0,
        "saved_tokens": 0,
    }


def _add_metrics(target: dict[str, int], row: sqlite3.Row) -> None:
    target["calls"] += 1
    if row["total_tokens"] is not None:
        target["actual_token_calls"] += 1
        target["worker_tokens"] += int(row["total_tokens"])
    target["delegated_tokens"] += int(row["delegated_context_tokens_estimate"] or 0)
    target["returned_tokens"] += int(row["returned_result_tokens_estimate"] or 0)
    target["saved_tokens"] += int(row["estimated_main_tokens_saved"] or 0)


def _append_range(clauses: list[str], params: list[Any], range_name: str) -> None:
    days = {"7d": 7, "30d": 30, "12m": 366}.get(range_name)
    if days:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        clauses.append("s.created_at >= ?" if any("s." in item for item in clauses) else "created_at >= ?")
        params.append(cutoff.strftime("%Y-%m-%d %H:%M:%S"))


def _bucket_keys(
    range_name: str, bucket: str, tz: ZoneInfo, rows: list[sqlite3.Row]
) -> list[str]:
    now = datetime.now(tz)
    if range_name == "7d":
        start = now - timedelta(days=6)
    elif range_name == "30d":
        start = now - timedelta(days=29)
    elif range_name == "12m":
        start = _shift_month(now.replace(day=1), -11)
    elif rows:
        start = _parse_utc(rows[0]["created_at"]).astimezone(tz)
    else:
        start = now
    if bucket == "month":
        cursor = start.replace(day=1)
        end = now.replace(day=1)
        keys = []
        while cursor <= end:
            keys.append(cursor.strftime("%Y-%m"))
            cursor = _shift_month(cursor, 1)
        return keys
    cursor = start.date()
    end = now.date()
    keys = []
    while cursor <= end:
        keys.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return keys


def _shift_month(value: datetime, amount: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + amount
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _utc_iso(value: str) -> str:
    return _parse_utc(value).isoformat().replace("+00:00", "Z")


def _call_row(item: dict[str, Any]) -> dict[str, Any]:
    item["created_at"] = _utc_iso(item["created_at"])
    item["accepted"] = bool(item["accepted"]) if item["accepted"] is not None else None
    if item["accepted"] is True:
        item["display_status"] = "accepted"
    elif item["accepted"] is False:
        item["display_status"] = "rejected"
    elif item.get("status") and item["status"] != "success":
        item["display_status"] = "error"
    else:
        item["display_status"] = item.get("status") or "unknown"
    return item


def _load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}
