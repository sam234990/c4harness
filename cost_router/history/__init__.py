"""Cross-task execution history and derived capability evidence.

This package is intentionally separate from ``cost_router.memory``. Memory is
the task-scoped collaboration graph; history is append-only evidence consumed
by analytics and future decomposition decisions.
"""

from .contracts import (
    CapabilityEvidence,
    ExecutionOutcome,
    FailureAttribution,
    OutcomeStatus,
    PlanSnapshot,
)
from .profiles import CapabilityProfile, build_capability_profile
from .repository import ExecutionHistoryRepository, InMemoryHistoryRepository
from .store import SQLiteHistoryRepository

__all__ = [
    "CapabilityEvidence",
    "CapabilityProfile",
    "ExecutionHistoryRepository",
    "ExecutionOutcome",
    "FailureAttribution",
    "InMemoryHistoryRepository",
    "OutcomeStatus",
    "PlanSnapshot",
    "SQLiteHistoryRepository",
    "build_capability_profile",
]
