"""Backward-compatible asynchronous runtime imports and module entry point."""

from .delegator.async_runtime import (
    AsyncTaskConfig,
    AsyncTaskRuntime,
    AsyncTaskStore,
    ClaudeWorkerSession,
    WorkerObservation,
    build_snapshot,
    runtime_main,
)

__all__ = [
    "AsyncTaskConfig",
    "AsyncTaskRuntime",
    "AsyncTaskStore",
    "ClaudeWorkerSession",
    "WorkerObservation",
    "build_snapshot",
    "runtime_main",
]


if __name__ == "__main__":
    raise SystemExit(runtime_main())
