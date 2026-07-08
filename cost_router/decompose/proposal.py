"""Codex-authored task proposal contracts and parsing.

Implements the CodexTaskProposal schema described in docs/decompose.md:
a versioned, structured proposal containing root goal, requirements,
constraints, acceptance criteria, nodes with capabilities and verifier
plans, interaction mode, and unresolved questions.

Design goals:
- Typed dataclasses with to_dict/from_dict round-trip.
- Strict unknown-field rejection with actionable JSON-path errors.
- Deterministic validation: duplicate IDs, dangling refs, invalid enums,
  malformed capability weights, inconsistent node references.
- Standard-library only; no external schema or validation dependencies.
- Separation from TaskContractGraph and Shared Memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Enums – reused from existing models where possible, but proposal-local
# enums are defined here to keep separation from the runtime graph types.
# ---------------------------------------------------------------------------

from .models import (
    ExecutionMode,
    InteractionMode,
    NodeKind,
    RequirementKind,
)

# ---------------------------------------------------------------------------
# Strict parsing helpers
# ---------------------------------------------------------------------------


class ProposalParseError(Exception):
    """Raised when a CodexTaskProposal dict fails schema or validation."""

    def __init__(self, message: str, json_path: str = "") -> None:
        self.json_path = json_path
        prefix = f"[{json_path}] " if json_path else ""
        super().__init__(f"{prefix}{message}")


def _check_unknown_fields(
    data: dict[str, Any], known: set[str], path: str
) -> None:
    """Reject any key not in *known*, raising ProposalParseError."""
    unknown = sorted(set(data) - known)
    if unknown:
        raise ProposalParseError(
            f"unknown field(s): {', '.join(unknown)}", path
        )


def _require(data: dict[str, Any], key: str, path: str) -> Any:
    """Return *data[key]* or raise if missing."""
    if key not in data:
        raise ProposalParseError(f"missing required field: {key}", path)
    return data[key]


def _require_str(data: dict[str, Any], key: str, path: str) -> str:
    val = _require(data, key, path)
    if not isinstance(val, str):
        raise ProposalParseError(
            f"field '{key}' must be a string, got {type(val).__name__}", path
        )
    if not val.strip():
        raise ProposalParseError(
            f"field '{key}' must not be empty", path
        )
    return val


def _require_list(data: dict[str, Any], key: str, path: str) -> list[Any]:
    val = _require(data, key, path)
    if not isinstance(val, list):
        raise ProposalParseError(
            f"field '{key}' must be a list, got {type(val).__name__}", path
        )
    return val


def _optional_list(data: dict[str, Any], key: str, path: str) -> list[Any]:
    val = data.get(key, [])
    if not isinstance(val, list):
        raise ProposalParseError(
            f"field '{key}' must be a list, got {type(val).__name__}", path
        )
    return val


def _optional_str_list(data: dict[str, Any], key: str, path: str) -> list[str]:
    raw = _optional_list(data, key, path)
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise ProposalParseError(
                f"item {i} must be a string, got {type(item).__name__}",
                f"{path}[{i}]",
            )
    return raw


def _parse_enum(
    raw: str, enum_cls: type, path: str, field_name: str
) -> Any:
    """Parse a string into an enum member or raise."""
    try:
        return enum_cls(raw)
    except ValueError:
        valid = ", ".join(m.value for m in enum_cls)
        raise ProposalParseError(
            f"invalid {field_name}: '{raw}' (valid: {valid})", path
        ) from None


def _parse_float(
    data: dict[str, Any], key: str, path: str, *, required: bool = False
) -> float:
    if required:
        val = _require(data, key, path)
    else:
        val = data.get(key, 0.0)
    if not isinstance(val, (int, float)):
        raise ProposalParseError(
            f"field '{key}' must be a number, got {type(val).__name__}", path
        )
    return float(val)


def _parse_int(
    data: dict[str, Any], key: str, path: str, *, required: bool = False
) -> int:
    if required:
        val = _require(data, key, path)
    else:
        val = data.get(key, 0)
    if not isinstance(val, int) or isinstance(val, bool):
        raise ProposalParseError(
            f"field '{key}' must be an integer, got {type(val).__name__}", path
        )
    return val


def _parse_bool(
    data: dict[str, Any], key: str, path: str, *, default: bool = False
) -> bool:
    val = data.get(key, default)
    if not isinstance(val, bool):
        raise ProposalParseError(
            f"field '{key}' must be a boolean, got {type(val).__name__}", path
        )
    return val


# ---------------------------------------------------------------------------
# Capability weight validation
# ---------------------------------------------------------------------------

_VALID_SOFT_CAPABILITIES: set[str] = {
    "code_implementation",
    "debugging",
    "frontend_visual",
    "documentation",
    "architecture",
    "long_context",
    "test_generation",
}


def _parse_capability_weights(
    data: dict[str, Any], key: str, path: str
) -> dict[str, float]:
    """Parse soft_capability_weights: dict[str, float] with range [0, 1]."""
    raw = data.get(key, {})
    if not isinstance(raw, dict):
        raise ProposalParseError(
            f"field '{key}' must be a dict, got {type(raw).__name__}", path
        )
    weights: dict[str, float] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            raise ProposalParseError(
                f"weight key must be a string, got {type(k).__name__}",
                f"{path}.{k}",
            )
        if isinstance(v, bool):
            raise ProposalParseError(
                f"weight '{k}' must be a number, got {type(v).__name__}",
                f"{path}.{k}",
            )
        if not isinstance(v, (int, float)):
            raise ProposalParseError(
                f"weight '{k}' must be a number, got {type(v).__name__}",
                f"{path}.{k}",
            )
        fv = float(v)
        if not (0.0 <= fv <= 1.0):
            raise ProposalParseError(
                f"weight '{k}' must be in [0, 1], got {fv}",
                f"{path}.{k}",
            )
        weights[k] = fv
    return weights


def _parse_hard_capabilities(
    data: dict[str, Any], path: str
) -> dict[str, Any]:
    """Parse hard_capabilities dict with known fields only."""
    raw = data.get("hard_capabilities", {})
    if not isinstance(raw, dict):
        raise ProposalParseError(
            f"field 'hard_capabilities' must be a dict, got {type(raw).__name__}",
            path,
        )
    known = {
        "modalities",
        "tools",
        "write_isolation",
        "network_required",
        "structured_output_required",
        "min_context_tokens",
        "persistent_session_required",
        "provider_protocols",
        "privacy_zones",
    }
    _check_unknown_fields(raw, known, f"{path}.hard_capabilities")

    result: dict[str, Any] = {}
    for list_key in ("modalities", "tools", "write_isolation", "provider_protocols", "privacy_zones"):
        result[list_key] = _optional_str_list(raw, list_key, f"{path}.hard_capabilities")
    result["network_required"] = _parse_bool(raw, "network_required", f"{path}.hard_capabilities")
    result["structured_output_required"] = _parse_bool(raw, "structured_output_required", f"{path}.hard_capabilities")
    result["min_context_tokens"] = _parse_int(raw, "min_context_tokens", f"{path}.hard_capabilities")
    result["persistent_session_required"] = _parse_bool(raw, "persistent_session_required", f"{path}.hard_capabilities")
    return result


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProposalRequirement:
    """Single requirement in a CodexTaskProposal."""

    id: str
    text: str
    kind: RequirementKind = RequirementKind.DELIVERABLE
    required: bool = True

    _KNOWN_FIELDS: ClassVar[set[str]] = {"id", "text", "kind", "required"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind.value,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: str = "requirements[]") -> ProposalRequirement:
        _check_unknown_fields(data, cls._KNOWN_FIELDS, path)
        rid = _require_str(data, "id", path)
        text = _require_str(data, "text", path)
        kind_raw = data.get("kind", RequirementKind.DELIVERABLE.value)
        if isinstance(kind_raw, str):
            kind = _parse_enum(kind_raw, RequirementKind, path, "kind")
        else:
            raise ProposalParseError(
                f"field 'kind' must be a string, got {type(kind_raw).__name__}", path
            )
        required = _parse_bool(data, "required", path, default=True)
        return cls(id=rid, text=text, kind=kind, required=required)


@dataclass(frozen=True, slots=True)
class ProposalAcceptanceCriterion:
    """Acceptance criterion in a CodexTaskProposal."""

    id: str
    description: str
    check: str = "semantic_review"
    requirement_refs: tuple[str, ...] = ()

    _KNOWN_FIELDS: ClassVar[set[str]] = {"id", "description", "check", "requirement_refs"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "check": self.check,
            "requirement_refs": list(self.requirement_refs),
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], path: str = "acceptance_criteria[]"
    ) -> ProposalAcceptanceCriterion:
        _check_unknown_fields(data, cls._KNOWN_FIELDS, path)
        cid = _require_str(data, "id", path)
        desc = _require_str(data, "description", path)
        check = data.get("check", "semantic_review")
        if not isinstance(check, str):
            raise ProposalParseError(
                f"field 'check' must be a string, got {type(check).__name__}", path
            )
        refs_raw = _optional_str_list(data, "requirement_refs", path)
        return cls(id=cid, description=desc, check=check, requirement_refs=tuple(refs_raw))


@dataclass(frozen=True, slots=True)
class VerifierPlan:
    """Verification design for a proposal node."""

    template_checks: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    semantic_criteria: tuple[str, ...] = ()
    root_contribution: str = ""
    inconclusive_policy: str = "fail"

    _KNOWN_FIELDS: ClassVar[set[str]] = {
        "template_checks",
        "evidence_requirements",
        "semantic_criteria",
        "root_contribution",
        "inconclusive_policy",
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_checks": list(self.template_checks),
            "evidence_requirements": list(self.evidence_requirements),
            "semantic_criteria": list(self.semantic_criteria),
            "root_contribution": self.root_contribution,
            "inconclusive_policy": self.inconclusive_policy,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], path: str = "verifier_plan"
    ) -> VerifierPlan:
        _check_unknown_fields(data, cls._KNOWN_FIELDS, path)
        template = _optional_str_list(data, "template_checks", path)
        evidence = _optional_str_list(data, "evidence_requirements", path)
        semantic = _optional_str_list(data, "semantic_criteria", path)
        contribution = data.get("root_contribution", "")
        if not isinstance(contribution, str):
            raise ProposalParseError(
                f"field 'root_contribution' must be a string, got {type(contribution).__name__}",
                path,
            )
        inconclusive = data.get("inconclusive_policy", "fail")
        if not isinstance(inconclusive, str):
            raise ProposalParseError(
                f"field 'inconclusive_policy' must be a string, got {type(inconclusive).__name__}",
                path,
            )
        return cls(
            template_checks=tuple(template),
            evidence_requirements=tuple(evidence),
            semantic_criteria=tuple(semantic),
            root_contribution=contribution,
            inconclusive_policy=inconclusive,
        )


@dataclass(frozen=True, slots=True)
class ProposalNode:
    """A single task node within a CodexTaskProposal."""

    node_id: str
    objective: str
    kind: NodeKind = NodeKind.WORK
    requirement_refs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    context_packs: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    artifact_inputs: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()
    execution_mode: ExecutionMode = ExecutionMode.READ_ONLY
    output_type: str = "report"
    hard_capabilities: dict[str, Any] = field(default_factory=dict)
    soft_capability_weights: dict[str, float] = field(default_factory=dict)
    verifier_plan: VerifierPlan = field(default_factory=VerifierPlan)
    root_contribution: str = ""

    _KNOWN_FIELDS: ClassVar[set[str]] = {
        "node_id",
        "objective",
        "kind",
        "requirement_refs",
        "dependencies",
        "context_packs",
        "allowed_paths",
        "artifact_inputs",
        "write_paths",
        "execution_mode",
        "output_type",
        "hard_capabilities",
        "soft_capability_weights",
        "verifier_plan",
        "root_contribution",
    }

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "objective": self.objective,
            "kind": self.kind.value,
            "requirement_refs": list(self.requirement_refs),
            "dependencies": list(self.dependencies),
            "context_packs": list(self.context_packs),
            "allowed_paths": list(self.allowed_paths),
            "artifact_inputs": list(self.artifact_inputs),
            "write_paths": list(self.write_paths),
            "execution_mode": self.execution_mode.value,
            "output_type": self.output_type,
            "hard_capabilities": dict(self.hard_capabilities),
            "soft_capability_weights": dict(sorted(self.soft_capability_weights.items())),
            "verifier_plan": self.verifier_plan.to_dict(),
            "root_contribution": self.root_contribution,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], path: str = "nodes[]"
    ) -> ProposalNode:
        _check_unknown_fields(data, cls._KNOWN_FIELDS, path)
        node_id = _require_str(data, "node_id", path)
        objective = _require_str(data, "objective", path)
        kind_raw = data.get("kind", NodeKind.WORK.value)
        if isinstance(kind_raw, str):
            kind = _parse_enum(kind_raw, NodeKind, path, "kind")
        else:
            raise ProposalParseError(
                f"field 'kind' must be a string, got {type(kind_raw).__name__}", path
            )
        req_refs = _optional_str_list(data, "requirement_refs", path)
        deps = _optional_str_list(data, "dependencies", path)
        ctx = _optional_str_list(data, "context_packs", path)
        allowed = _optional_str_list(data, "allowed_paths", path)
        artifact_inputs = _optional_str_list(data, "artifact_inputs", path)
        write_paths = _optional_str_list(data, "write_paths", path)

        em_raw = data.get("execution_mode", ExecutionMode.READ_ONLY.value)
        if isinstance(em_raw, str):
            execution_mode = _parse_enum(em_raw, ExecutionMode, path, "execution_mode")
        else:
            raise ProposalParseError(
                f"field 'execution_mode' must be a string, got {type(em_raw).__name__}", path
            )

        output_type = data.get("output_type", "report")
        if not isinstance(output_type, str):
            raise ProposalParseError(
                f"field 'output_type' must be a string, got {type(output_type).__name__}", path
            )

        hard = _parse_hard_capabilities(data, path)
        soft = _parse_capability_weights(data, "soft_capability_weights", path)
        vp_raw = data.get("verifier_plan", {})
        if not isinstance(vp_raw, dict):
            raise ProposalParseError(
                f"field 'verifier_plan' must be a dict, got {type(vp_raw).__name__}",
                path,
            )
        verifier = VerifierPlan.from_dict(vp_raw, f"{path}.verifier_plan")
        contribution = data.get("root_contribution", "")
        if not isinstance(contribution, str):
            raise ProposalParseError(
                f"field 'root_contribution' must be a string, got {type(contribution).__name__}",
                path,
            )
        return cls(
            node_id=node_id,
            objective=objective,
            kind=kind,
            requirement_refs=tuple(req_refs),
            dependencies=tuple(deps),
            context_packs=tuple(ctx),
            allowed_paths=tuple(allowed),
            artifact_inputs=tuple(artifact_inputs),
            write_paths=tuple(write_paths),
            execution_mode=execution_mode,
            output_type=output_type,
            hard_capabilities=hard,
            soft_capability_weights=soft,
            verifier_plan=verifier,
            root_contribution=contribution,
        )


# ---------------------------------------------------------------------------
# Top-level proposal
# ---------------------------------------------------------------------------

_PROPOSAL_KNOWN_FIELDS: set[str] = {
    "version",
    "root_goal",
    "requirements",
    "constraints",
    "acceptance_criteria",
    "interaction_mode",
    "unresolved_questions",
    "nodes",
}


@dataclass(slots=True)
class CodexTaskProposal:
    """A versioned task proposal emitted by Codex and validated by C4Harness.

    Fields follow the CodexTaskProposal schema in docs/decompose.md.
    """

    version: int
    root_goal: str = ""
    requirements: list[ProposalRequirement] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[ProposalAcceptanceCriterion] = field(
        default_factory=list
    )
    interaction_mode: InteractionMode = InteractionMode.EXECUTE
    unresolved_questions: list[str] = field(default_factory=list)
    nodes: list[ProposalNode] = field(default_factory=list)

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "root_goal": self.root_goal,
            "requirements": [r.to_dict() for r in self.requirements],
            "constraints": list(self.constraints),
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "interaction_mode": self.interaction_mode.value,
            "unresolved_questions": list(self.unresolved_questions),
            "nodes": [n.to_dict() for n in self.nodes],
        }

    def to_json(self) -> str:
        """Serialise to JSON string (stdlib json)."""
        import json

        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    # -- parsing -------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodexTaskProposal:
        """Parse a CodexTaskProposal from a plain dict with strict validation.

        Raises ProposalParseError on schema violations, unknown fields,
        duplicate IDs, dangling references, invalid enums, malformed
        capability weights, or inconsistent node references.
        """
        if not isinstance(data, dict):
            raise ProposalParseError(
                f"proposal must be a dict, got {type(data).__name__}", "$"
            )
        _check_unknown_fields(data, _PROPOSAL_KNOWN_FIELDS, "$")

        version = _parse_int(data, "version", "$", required=True)
        if version != 1:
            raise ProposalParseError(
                f"unsupported schema version: {version} (only version 1 is supported)", "$"
            )
        root_goal = _require_str(data, "root_goal", "$")

        # requirements
        req_raw = _require_list(data, "requirements", "$")
        requirements: list[ProposalRequirement] = []
        req_ids: set[str] = set()
        for i, item in enumerate(req_raw):
            if not isinstance(item, dict):
                raise ProposalParseError(
                    f"item must be a dict, got {type(item).__name__}",
                    f"$.requirements[{i}]",
                )
            req = ProposalRequirement.from_dict(item, f"$.requirements[{i}]")
            if req.id in req_ids:
                raise ProposalParseError(
                    f"duplicate requirement id: '{req.id}'",
                    f"$.requirements[{i}]",
                )
            req_ids.add(req.id)
            requirements.append(req)

        # constraints
        constraints = _optional_str_list(data, "constraints", "$")

        # acceptance_criteria
        ac_raw = _optional_list(data, "acceptance_criteria", "$")
        criteria: list[ProposalAcceptanceCriterion] = []
        ac_ids: set[str] = set()
        for i, item in enumerate(ac_raw):
            if not isinstance(item, dict):
                raise ProposalParseError(
                    f"item must be a dict, got {type(item).__name__}",
                    f"$.acceptance_criteria[{i}]",
                )
            ac = ProposalAcceptanceCriterion.from_dict(
                item, f"$.acceptance_criteria[{i}]"
            )
            if ac.id in ac_ids:
                raise ProposalParseError(
                    f"duplicate acceptance criterion id: '{ac.id}'",
                    f"$.acceptance_criteria[{i}]",
                )
            ac_ids.add(ac.id)
            criteria.append(ac)

        # interaction_mode
        im_raw = data.get("interaction_mode", InteractionMode.EXECUTE.value)
        if isinstance(im_raw, str):
            interaction_mode = _parse_enum(
                im_raw, InteractionMode, "$", "interaction_mode"
            )
        else:
            raise ProposalParseError(
                f"field 'interaction_mode' must be a string, got {type(im_raw).__name__}",
                "$",
            )

        # unresolved_questions
        questions = _optional_str_list(data, "unresolved_questions", "$")

        # nodes
        nodes_raw = _require_list(data, "nodes", "$")
        nodes: list[ProposalNode] = []
        node_ids: set[str] = set()
        for i, item in enumerate(nodes_raw):
            if not isinstance(item, dict):
                raise ProposalParseError(
                    f"item must be a dict, got {type(item).__name__}",
                    f"$.nodes[{i}]",
                )
            node = ProposalNode.from_dict(item, f"$.nodes[{i}]")
            if node.node_id in node_ids:
                raise ProposalParseError(
                    f"duplicate node id: '{node.node_id}'",
                    f"$.nodes[{i}]",
                )
            node_ids.add(node.node_id)
            nodes.append(node)

        proposal = cls(
            version=version,
            root_goal=root_goal,
            requirements=requirements,
            constraints=constraints,
            acceptance_criteria=criteria,
            interaction_mode=interaction_mode,
            unresolved_questions=questions,
            nodes=nodes,
        )

        # Cross-field validation
        proposal._validate_references(req_ids, node_ids)
        return proposal

    @classmethod
    def from_json(cls, text: str) -> CodexTaskProposal:
        """Parse from a JSON string."""
        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProposalParseError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)

    # -- cross-field validation ----------------------------------------------

    def _validate_references(
        self, req_ids: set[str], node_ids: set[str]
    ) -> None:
        """Check requirement refs, dependency refs, and dangling references."""
        # Node requirement_refs must reference declared requirements
        for node in self.nodes:
            for ref in node.requirement_refs:
                if ref not in req_ids:
                    raise ProposalParseError(
                        f"node '{node.node_id}' references unknown requirement: '{ref}'",
                        f"$.nodes[{node.node_id}].requirement_refs",
                    )

        # Node dependencies must reference other declared nodes
        for node in self.nodes:
            for dep in node.dependencies:
                if dep not in node_ids:
                    raise ProposalParseError(
                        f"node '{node.node_id}' depends on unknown node: '{dep}'",
                        f"$.nodes[{node.node_id}].dependencies",
                    )
                if dep == node.node_id:
                    raise ProposalParseError(
                        f"node '{node.node_id}' cannot depend on itself",
                        f"$.nodes[{node.node_id}].dependencies",
                    )

        # Acceptance criterion requirement_refs must reference declared requirements
        for ac in self.acceptance_criteria:
            for ref in ac.requirement_refs:
                if ref not in req_ids:
                    raise ProposalParseError(
                        f"acceptance criterion '{ac.id}' references unknown requirement: '{ref}'",
                        f"$.acceptance_criteria[{ac.id}].requirement_refs",
                    )

        # Reject capability weights with unknown dimension names
        for node in self.nodes:
            for key in node.soft_capability_weights:
                if key not in _VALID_SOFT_CAPABILITIES:
                    raise ProposalParseError(
                        f"unknown soft capability dimension: '{key}' "
                        f"(valid: {', '.join(sorted(_VALID_SOFT_CAPABILITIES))})",
                        f"$.nodes[{node.node_id}].soft_capability_weights",
                    )
