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
from .compiler import ProposalCompileError, compile_proposal
from .proposal import (
    CodexTaskProposal,
    ProposalAcceptanceCriterion,
    ProposalNode,
    ProposalParseError,
    ProposalRequirement,
    VerifierPlan,
)
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
    "CodexTaskProposal",
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
    "ProposalAcceptanceCriterion",
    "ProposalCompileError",
    "ProposalNode",
    "ProposalParseError",
    "ProposalRequirement",
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
    "VerifierPlan",
    "WorkerArm",
    "WorkerAssignmentPolicy",
    "WorkerCapabilities",
    "WorkerRegistry",
    "match_capabilities",
    "assess_shape",
    "check_atomicity",
    "choose_primary_split",
    "compute_confidence",
    "compile_proposal",
]
