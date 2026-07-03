"""Task-situation grounding and contract-graph planning."""

from .capabilities import CapabilityMatch, WorkerRegistry, match_capabilities
from .models import (
    AcceptanceCriterion,
    DecompositionPlan,
    ExecutionMode,
    ExecutionShape,
    GraphEdge,
    HardCapabilityRequirements,
    InteractionMode,
    NodeKind,
    Requirement,
    RequirementKind,
    RequirementLedger,
    RootContract,
    TaskContractGraph,
    TaskNodeContract,
    TaskSituation,
    VerificationContract,
    WorkerArm,
    WorkerCapabilities,
)
from .planner import DecompositionPlanner, TaskSituationBuilder
from .service import DecompositionService

__all__ = [
    "AcceptanceCriterion",
    "CapabilityMatch",
    "DecompositionPlan",
    "DecompositionPlanner",
    "DecompositionService",
    "ExecutionMode",
    "ExecutionShape",
    "GraphEdge",
    "HardCapabilityRequirements",
    "InteractionMode",
    "NodeKind",
    "Requirement",
    "RequirementKind",
    "RequirementLedger",
    "RootContract",
    "TaskContractGraph",
    "TaskNodeContract",
    "TaskSituation",
    "TaskSituationBuilder",
    "VerificationContract",
    "WorkerArm",
    "WorkerCapabilities",
    "WorkerRegistry",
    "match_capabilities",
]
