from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class InteractionMode(str, Enum):
    EXECUTE = "execute"
    PLAN = "plan"


class RequirementKind(str, Enum):
    DELIVERABLE = "deliverable"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"
    ACCEPTANCE = "acceptance"


class NodeKind(str, Enum):
    PROBE = "probe"
    WORK = "work"
    VERIFY = "verify"
    MERGE = "merge"
    DECISION = "decision"
    WAIT = "wait"


class ExecutionMode(str, Enum):
    READ_ONLY = "read_only"
    PATCH = "patch"
    EXECUTE = "execute"
    MONITOR = "monitor"


class ExecutionShape(str, Enum):
    FAST_PATH = "fast_path"
    GRAPH = "graph"


@dataclass(frozen=True, slots=True)
class Requirement:
    id: str
    text: str
    kind: RequirementKind = RequirementKind.DELIVERABLE
    required: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Requirement id cannot be empty.")
        if not self.text.strip():
            raise ValueError("Requirement text cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind.value,
            "required": self.required,
        }


@dataclass(slots=True)
class RequirementLedger:
    items: list[Requirement] = field(default_factory=list)

    def __post_init__(self) -> None:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Requirement ids must be unique.")

    def required_ids(self) -> set[str]:
        return {item.id for item in self.items if item.required}

    def deliverables(self) -> list[Requirement]:
        return [item for item in self.items if item.kind == RequirementKind.DELIVERABLE]

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items]}


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    id: str
    description: str
    check: str = "semantic_review"
    requirement_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.description.strip():
            raise ValueError("Acceptance criterion id and description are required.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "check": self.check,
            "requirement_refs": list(self.requirement_refs),
        }


@dataclass(slots=True)
class RootContract:
    criteria: list[AcceptanceCriterion]
    merge_strategy: str = "orchestrator_review"

    def __post_init__(self) -> None:
        if not self.criteria:
            raise ValueError("Root contract requires at least one acceptance criterion.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "merge_strategy": self.merge_strategy,
        }


@dataclass(frozen=True, slots=True)
class HardCapabilityRequirements:
    modalities: frozenset[str] = frozenset({"text"})
    tools: frozenset[str] = frozenset()
    write_isolation: frozenset[str] = frozenset()
    network_required: bool = False
    structured_output_required: bool = False
    min_context_tokens: int = 0
    persistent_session_required: bool = False
    provider_protocols: frozenset[str] = frozenset()
    privacy_zones: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "modalities": sorted(self.modalities),
            "tools": sorted(self.tools),
            "write_isolation": sorted(self.write_isolation),
            "network_required": self.network_required,
            "structured_output_required": self.structured_output_required,
            "min_context_tokens": self.min_context_tokens,
            "persistent_session_required": self.persistent_session_required,
            "provider_protocols": sorted(self.provider_protocols),
            "privacy_zones": sorted(self.privacy_zones),
        }


@dataclass(frozen=True, slots=True)
class WorkerCapabilities:
    modalities: frozenset[str] = frozenset({"text"})
    tools: frozenset[str] = frozenset({"read"})
    write_isolation: str = "none"
    network: bool = False
    structured_output: bool = False
    context_tokens: int = 0
    persistent_session: bool = False
    provider_protocol: str = "harness_native"
    privacy_zone: str = "approved_external"
    soft: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "modalities": sorted(self.modalities),
            "tools": sorted(self.tools),
            "write_isolation": self.write_isolation,
            "network": self.network,
            "structured_output": self.structured_output,
            "context_tokens": self.context_tokens,
            "persistent_session": self.persistent_session,
            "provider_protocol": self.provider_protocol,
            "privacy_zone": self.privacy_zone,
            "soft": dict(sorted(self.soft.items())),
        }


@dataclass(frozen=True, slots=True)
class WorkerArm:
    id: str
    backend: str
    harness: str
    model: str
    model_version: str | None = None
    policy_profile: str = "default"
    enabled: bool = True
    capabilities: WorkerCapabilities = field(default_factory=WorkerCapabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backend": self.backend,
            "harness": self.harness,
            "model": self.model,
            "model_version": self.model_version,
            "policy_profile": self.policy_profile,
            "enabled": self.enabled,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class VerificationContract:
    deterministic_checks: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    semantic_check: str | None = None
    root_contribution: str = ""

    def is_verifiable(self) -> bool:
        return bool(
            self.deterministic_checks
            or self.evidence_requirements
            or self.semantic_check
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deterministic_checks": list(self.deterministic_checks),
            "evidence_requirements": list(self.evidence_requirements),
            "semantic_check": self.semantic_check,
            "root_contribution": self.root_contribution,
        }


@dataclass(slots=True)
class TaskNodeContract:
    objective: str
    kind: NodeKind = NodeKind.WORK
    id: str = field(default_factory=lambda: f"node_{uuid4().hex[:12]}")
    requirement_refs: tuple[str, ...] = ()
    context_packs: tuple[Path, ...] = ()
    artifact_inputs: tuple[str, ...] = ()
    allowed_paths: tuple[Path, ...] = ()
    write_paths: tuple[Path, ...] = ()
    output_type: str = "report"
    execution_mode: ExecutionMode = ExecutionMode.READ_ONLY
    hard_capabilities: HardCapabilityRequirements = field(
        default_factory=HardCapabilityRequirements
    )
    soft_capabilities: dict[str, float] = field(default_factory=dict)
    verification: VerificationContract = field(default_factory=VerificationContract)
    max_attempts: int = 1
    assigned_worker_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.objective.strip():
            raise ValueError("Task node id and objective are required.")
        if self.max_attempts < 1:
            raise ValueError("Task node max_attempts must be at least one.")
        if self.execution_mode == ExecutionMode.PATCH and not self.write_paths:
            raise ValueError("Patch task nodes require at least one write path.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "objective": self.objective,
            "requirement_refs": list(self.requirement_refs),
            "context_packs": [str(path) for path in self.context_packs],
            "artifact_inputs": list(self.artifact_inputs),
            "allowed_paths": [str(path) for path in self.allowed_paths],
            "write_paths": [str(path) for path in self.write_paths],
            "output_type": self.output_type,
            "execution_mode": self.execution_mode.value,
            "hard_capabilities": self.hard_capabilities.to_dict(),
            "soft_capabilities": dict(sorted(self.soft_capabilities.items())),
            "verification": self.verification.to_dict(),
            "max_attempts": self.max_attempts,
            "assigned_worker_id": self.assigned_worker_id,
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str = "requires"

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
        }


@dataclass(slots=True)
class TaskContractGraph:
    nodes: dict[str, TaskNodeContract] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    version: int = 1

    def add_node(self, node: TaskNodeContract) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate task node id: {node.id}")
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("Graph edges must reference existing nodes.")
        if edge.source == edge.target:
            raise ValueError("Task graph cannot contain self edges.")
        self.edges.append(edge)
        try:
            self.validate_acyclic()
        except ValueError:
            self.edges.pop()
            raise

    def validate_acyclic(self) -> None:
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for edge in self.edges:
            outgoing[edge.source].append(edge.target)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Task contract graph must be acyclic.")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in outgoing[node_id]:
                visit(target)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.nodes:
            visit(node_id)

    def ready_nodes(self, completed: set[str] | None = None) -> list[TaskNodeContract]:
        completed = completed or set()
        blocked = {
            edge.target
            for edge in self.edges
            if edge.edge_type == "requires" and edge.source not in completed
        }
        return [
            node
            for node_id, node in self.nodes.items()
            if node_id not in completed and node_id not in blocked
        ]

    def requirement_coverage(self) -> set[str]:
        return {
            requirement_id
            for node in self.nodes.values()
            for requirement_id in node.requirement_refs
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(slots=True)
class TaskSituation:
    task_id: str
    objective: str
    repo: Path
    requirements: RequirementLedger
    root_contract: RootContract
    interaction_mode: InteractionMode = InteractionMode.EXECUTE
    active_skills: tuple[str, ...] = ()
    skill_steps: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    environment_facts: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    available_worker_ids: tuple[str, ...] = ()
    historical_profile_summary: tuple[str, ...] = ()
    security_context: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "repo": str(self.repo),
            "requirements": self.requirements.to_dict(),
            "root_contract": self.root_contract.to_dict(),
            "interaction_mode": self.interaction_mode.value,
            "active_skills": list(self.active_skills),
            "skill_steps": list(self.skill_steps),
            "constraints": list(self.constraints),
            "environment_facts": list(self.environment_facts),
            "unresolved_questions": list(self.unresolved_questions),
            "available_worker_ids": list(self.available_worker_ids),
            "historical_profile_summary": list(self.historical_profile_summary),
            "security_context": list(self.security_context),
        }


@dataclass(slots=True)
class DecompositionPlan:
    situation: TaskSituation
    shape: ExecutionShape
    graph: TaskContractGraph
    reasons: list[str] = field(default_factory=list)
    assignment_records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.graph.nodes:
            raise ValueError("Decomposition plan requires at least one node.")
        self.graph.validate_acyclic()
        requirement_ids = {item.id for item in self.situation.requirements.items}
        referenced_ids = self.graph.requirement_coverage()
        unknown = referenced_ids - requirement_ids
        if unknown:
            raise ValueError(
                "Task graph references unknown requirements: " + ", ".join(sorted(unknown))
            )
        root_refs = {
            requirement_id
            for criterion in self.situation.root_contract.criteria
            for requirement_id in criterion.requirement_refs
        }
        unknown_root_refs = root_refs - requirement_ids
        if unknown_root_refs:
            raise ValueError(
                "Root contract references unknown requirements: "
                + ", ".join(sorted(unknown_root_refs))
            )
        missing = self.situation.requirements.required_ids() - referenced_ids
        if missing:
            raise ValueError(
                "Task graph does not cover required requirements: " + ", ".join(sorted(missing))
            )
        unverifiable = [
            node.id
            for node in self.graph.nodes.values()
            if node.kind in {NodeKind.PROBE, NodeKind.WORK, NodeKind.MERGE}
            and not node.verification.is_verifiable()
        ]
        if unverifiable:
            raise ValueError(
                "Executable task nodes require verification contracts: "
                + ", ".join(unverifiable)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape.value,
            "reasons": self.reasons,
            "assignments": self.assignment_records,
            "situation": self.situation.to_dict(),
            "graph": self.graph.to_dict(),
        }
