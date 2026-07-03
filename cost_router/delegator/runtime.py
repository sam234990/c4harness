from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..core.contracts import RouteDecision, Task, VerificationResult, WorkerResult
from ..hooks import HookSet
from ..memory import MemoryStore
from ..verifier import verify_worker_result


WorkerRunner = Callable[..., WorkerResult]
DecisionFactory = Callable[[Task], RouteDecision]
PreparationFactory = Callable[[Task], "PreparedWorker"]
Verifier = Callable[[WorkerResult, Path, Task | None], VerificationResult]


@dataclass(slots=True)
class PreparedWorker:
    output_file: Path
    command: list[str]
    prompt: str
    runner: WorkerRunner
    agent_file: Path | None = None

    def public_dict(self, command: list[str] | None = None) -> dict[str, Any]:
        return {
            "agent_file": str(self.agent_file) if self.agent_file else None,
            "output_file": str(self.output_file),
            "prompt": self.prompt,
            "command": command if command is not None else self.command,
        }


@dataclass(slots=True)
class DelegationOutcome:
    task: Task
    decision: RouteDecision
    prepared: PreparedWorker
    executed: bool
    result: WorkerResult | None = None
    verification: VerificationResult | None = None


class DelegationRuntime:
    """Runs one task node through route, delegate, verify, and record.

    A future graph executor can call this class for each ready node. Backend
    selection and graph scheduling deliberately remain outside this boundary.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        hooks: HookSet | None = None,
        verifier: Verifier = verify_worker_result,
    ) -> None:
        self.store = store
        self.hooks = hooks or HookSet()
        self.verifier = verifier

    def dispatch(
        self,
        task: Task,
        *,
        decide: DecisionFactory,
        prepare: PreparationFactory,
        execute: bool,
    ) -> DelegationOutcome:
        # Fail before invoking a paid worker when the selected ledger cannot be opened.
        self.store.init()
        self.hooks.pre_route(task)
        decision = decide(task)
        self.hooks.post_route(task, decision)
        prepared = prepare(task)

        result: WorkerResult | None = None
        verification: VerificationResult | None = None
        if execute:
            self.hooks.pre_delegate(task, decision)
            try:
                result = prepared.runner(
                    task=task,
                    command=prepared.command,
                    output_file=prepared.output_file,
                    timeout_sec=task.constraints.max_runtime_sec,
                    cwd=task.repo,
                )
            except Exception as error:
                result = WorkerResult(
                    status="failed",
                    summary=f"Worker backend raised {type(error).__name__}: {error}",
                    risks=["The worker did not return a normal result."],
                    next_steps=["Inspect the backend error and retry only after it is resolved."],
                )
            self.hooks.post_delegate(task, result)
            verification = self.verifier(result, task.repo, task)
            self.hooks.post_verify(task, verification)
            self.store.record_subtask(
                task=task,
                decision=decision,
                result=result,
                verification=verification,
            )
        else:
            self.store.record_subtask(task=task, decision=decision)

        return DelegationOutcome(
            task=task,
            decision=decision,
            prepared=prepared,
            executed=execute,
            result=result,
            verification=verification,
        )
