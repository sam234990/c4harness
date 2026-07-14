"""Graph-scoped patch integration and workspace isolation.

Public API
----------
**Workspace lifecycle** (``workspace``):
    :func:`create_integration_snapshot` — build an isolated copy of a source
    directory for one graph execution node.

**Patch operations** (``patches``):
    :class:`PatchApplier` — validate and apply unified-diff hunks to a
    snapshot with allowlist enforcement and atomic replacement.

**Conflict detection** (``conflicts``):
    :class:`WriteReservationManager` — node-scoped write-set reservations
    without TTL; overlapping active writes conflict.
    :func:`detect_conflicts` — compare a baseline snapshot against the
    current source state and active reservations.
"""

from .conflicts import (
    Conflict,
    ConflictKind,
    ReservationRecord,
    WriteReservationManager,
    detect_conflicts,
)
from .patches import (
    ChangeKind,
    FileChange,
    PatchApplier,
    PatchHunk,
    PatchResult,
    generate_unified_diff,
    parse_unified_diff,
)
from .workspace import (
    EMPTY_DIR_SENTINEL,
    FileState,
    IntegrationResult,
    IntegrationSnapshot,
    create_integration_snapshot,
    normalize_repo_relative,
)
from .service import GraphIntegrationSession, IntegrationAttempt

__all__ = [
    # workspace
    "EMPTY_DIR_SENTINEL",
    "FileState",
    "IntegrationResult",
    "IntegrationSnapshot",
    "create_integration_snapshot",
    "normalize_repo_relative",
    # patches
    "ChangeKind",
    "FileChange",
    "PatchApplier",
    "PatchHunk",
    "PatchResult",
    "generate_unified_diff",
    "parse_unified_diff",
    # conflicts
    "Conflict",
    "ConflictKind",
    "ReservationRecord",
    "WriteReservationManager",
    "detect_conflicts",
    "GraphIntegrationSession",
    "IntegrationAttempt",
]
