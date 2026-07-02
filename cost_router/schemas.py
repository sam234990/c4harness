from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


class TaskMode(str, Enum):
    READ_ONLY = "read_only"
    PATCH = "patch"


class Difficulty(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    HARD = "hard"


class Risk(str, Enum):
    READ_ONLY = "read_only"
    PATCH = "patch"
    SENSITIVE = "sensitive"


@dataclass(slots=True)
class TaskConstraints:
    mode: TaskMode = TaskMode.READ_ONLY
    max_runtime_sec: int = 900
    allow_network: bool = False
    max_output_chars: int = 12000

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "max_runtime_sec": self.max_runtime_sec,
            "allow_network": self.allow_network,
            "max_output_chars": self.max_output_chars,
        }


@dataclass(slots=True)
class Task:
    goal: str
    paths: list[Path] = field(default_factory=list)
    write_paths: list[Path] = field(default_factory=list)
    context_packs: list[Path] = field(default_factory=list)
    repo: Path = field(default_factory=Path.cwd)
    id: str = field(default_factory=lambda: f"task_{uuid4().hex[:12]}")
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    parent_task_label: str | None = None
    source_thread_id: str | None = field(
        default_factory=lambda: os.environ.get("CODEX_THREAD_ID") or None
    )
    source_harness: str = field(
        default_factory=lambda: "codex" if os.environ.get("CODEX_THREAD_ID") else "cli"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "repo": str(self.repo),
            "paths": [str(path) for path in self.paths],
            "write_paths": [str(path) for path in self.write_paths],
            "context_packs": [str(path) for path in self.context_packs],
            "parent_task_label": self.parent_task_label,
            "source_thread_id": self.source_thread_id,
            "source_harness": self.source_harness,
            "constraints": self.constraints.to_dict(),
        }


@dataclass(slots=True)
class RouteDecision:
    difficulty: Difficulty
    risk: Risk
    can_delegate: bool
    backend: str
    worker: str
    model: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "difficulty": self.difficulty.value,
            "risk": self.risk.value,
            "can_delegate": self.can_delegate,
            "backend": self.backend,
            "worker": self.worker,
            "model": self.model,
            "reason": self.reason,
        }


@dataclass(slots=True)
class Evidence:
    path: str
    observation: str
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "observation": self.observation,
        }
        if self.line is not None:
            data["line"] = self.line
        return data


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "source": self.source,
        }


@dataclass(slots=True)
class TokenAnalysis:
    delegated_context_tokens_estimate: int | None = None
    returned_result_tokens_estimate: int | None = None
    estimated_main_tokens_saved: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegated_context_tokens_estimate": self.delegated_context_tokens_estimate,
            "returned_result_tokens_estimate": self.returned_result_tokens_estimate,
            "estimated_main_tokens_saved": self.estimated_main_tokens_saved,
        }


@dataclass(slots=True)
class WorkerResult:
    status: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    raw_output_path: Path | None = None
    proposed_patch_path: Path | None = None
    changed_paths: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    token_analysis: TokenAnalysis = field(default_factory=TokenAnalysis)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "risks": self.risks,
            "next_steps": self.next_steps,
            "raw_output_path": str(self.raw_output_path) if self.raw_output_path else None,
            "proposed_patch_path": (
                str(self.proposed_patch_path) if self.proposed_patch_path else None
            ),
            "changed_paths": self.changed_paths,
            "policy_violations": self.policy_violations,
            "token_usage": self.token_usage.to_dict(),
            "token_analysis": self.token_analysis.to_dict(),
        }


@dataclass(slots=True)
class VerificationResult:
    accepted: bool
    confidence: str
    issues: list[str] = field(default_factory=list)
    memory_facts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "confidence": self.confidence,
            "issues": self.issues,
            "memory_facts": self.memory_facts,
        }
