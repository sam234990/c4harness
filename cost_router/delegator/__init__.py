"""Worker execution and harness adapters.

Async runtime symbols are loaded lazily so ``python -m
cost_router.delegator.async_runtime`` can execute without importing the target
module through this package first.  The lazy exports preserve the existing
public import surface.
"""

from typing import TYPE_CHECKING, Any

from .runtime import DelegationOutcome, DelegationRuntime, PreparedWorker
from .scheduler import GraphResult, GraphScheduler, NodeOutcome, NodeState

if TYPE_CHECKING:
    from .async_runtime import (
        AsyncTaskConfig,
        AsyncTaskRuntime,
        AsyncTaskStore,
    )

__all__ = [
    "AsyncTaskConfig",
    "AsyncTaskRuntime",
    "AsyncTaskStore",
    "DelegationOutcome",
    "DelegationRuntime",
    "PreparedWorker",
    "GraphResult",
    "GraphScheduler",
    "NodeOutcome",
    "NodeState",
]


def __getattr__(name: str) -> Any:
    if name in {
        "AsyncTaskConfig",
        "AsyncTaskRuntime",
        "AsyncTaskStore",
    }:
        from . import async_runtime

        return getattr(async_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
