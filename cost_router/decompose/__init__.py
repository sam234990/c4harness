"""Task-situation grounding and contract-graph planning."""

from .capabilities import CapabilityMatch, WorkerRegistry, match_capabilities
from .assignment import (
    AssignmentCandidate,
    AssignmentDecision,
    ScoreBreakdown,
    WorkerAssignmentPolicy,
)
from .atomicity import AtomicityAssessment, ShapeAssessment, assess_shape, check_atomicity
from .confidence import ConfidenceFactors, compute_confidence
from .operators import SplitProposal, choose_primary_split
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
from .planner import DecompositionPlanner
from .situation import TaskSituationBuilder
from .service import DecompositionService
from .replan import (
    BoundedReplanner,
    ReplanAction,
    ReplanDecision,
    ReplanReason,
    ReplanRequest,
)

__all__ = [
    "AcceptanceCriterion",
    "AssignmentCandidate",
    "AssignmentDecision",
    "AtomicityAssessment",
    "BoundedReplanner",
    "ConfidenceFactors",
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
    "ReplanAction",
    "ReplanDecision",
    "ReplanReason",
    "ReplanRequest",
    "RootContract",
    "ScoreBreakdown",
    "ShapeAssessment",
    "SplitProposal",
    "TaskContractGraph",
    "TaskNodeContract",
    "TaskSituation",
    "TaskSituationBuilder",
    "VerificationContract",
    "WorkerArm",
    "WorkerAssignmentPolicy",
    "WorkerCapabilities",
    "WorkerRegistry",
    "match_capabilities",
    "assess_shape",
    "check_atomicity",
    "choose_primary_split",
    "compute_confidence",
]
