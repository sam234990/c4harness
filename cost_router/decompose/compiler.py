"""Deterministic compilation of Codex task proposals.

Compiles a CodexTaskProposal into a DecompositionPlan without calling
any model, executing workers, writing History, or modifying existing modules.

Invariants enforced:
- Proposal contains at least one node and one acceptance criterion.
- Every required requirement is referenced by at least one node.
- Every required deliverable is referenced by an acceptance criterion (root).
- Constraint-kind requirements never become standalone work nodes.
- Plan Mode forces all nodes to read-only.
- All declared paths resolve inside the repository.
- Execution mode and write-scope are consistent.
- Dependency graph is acyclic with no dangling references.
- Hard capabilities and soft weights are compiled to contract types.
- Worker assignment uses existing hard-filter/soft-score policy with risk manifests.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from .assignment import WorkerAssignmentPolicy
from .capabilities import WorkerRegistry
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
)
from .proposal import CodexTaskProposal, ProposalNode
from .verifier_templates import TemplateValidationError, validate_template_checks


class ProposalCompileError(Exception):
    """Raised when a CodexTaskProposal fails compilation validation."""


def compile_proposal(
    proposal: CodexTaskProposal,
    repo: Path,
    registry: WorkerRegistry,
    worker_preferences: dict[str, float] | None = None,
    capability_profiles: dict[str, object] | None = None,
) -> DecompositionPlan:
    """Compile a *CodexTaskProposal* into a *DecompositionPlan*.

    Validates requirement coverage, constraint preservation, graph structure,
    Plan Mode enforcement, path safety, execution mode consistency, and
    deliverable root contribution.  Then compiles hard/soft capabilities
    and runs deterministic worker assignment.

    Raises :class:`ProposalCompileError` on any invariant violation.
    Does not call a model, execute workers, or write History.
    """
    repo_resolved = repo.resolve()

    # -- Gate: non-empty nodes -----------------------------------------------
    if not proposal.nodes:
        raise ProposalCompileError("proposal must contain at least one node")

    # -- Gate: acceptance criteria for root contract -------------------------
    if not proposal.acceptance_criteria:
        raise ProposalCompileError(
            "proposal must contain at least one acceptance criterion "
            "to build the root contract"
        )

    # -- Requirement coverage ------------------------------------------------
    req_by_id = {r.id: r for r in proposal.requirements}
    required_ids = {r.id for r in proposal.requirements if r.required}
    node_ref_ids: set[str] = set()
    for node in proposal.nodes:
        node_ref_ids.update(node.requirement_refs)
    uncovered = required_ids - node_ref_ids
    if uncovered:
        raise ProposalCompileError(
            "required requirements not referenced by any node: "
            + ", ".join(sorted(uncovered))
        )

    # -- Required deliverables must contribute to root -----------------------
    required_deliverable_ids = {
        r.id
        for r in proposal.requirements
        if r.required and r.kind == RequirementKind.DELIVERABLE
    }
    ac_ref_ids: set[str] = set()
    for ac in proposal.acceptance_criteria:
        ac_ref_ids.update(ac.requirement_refs)
    unrooted = required_deliverable_ids - ac_ref_ids
    if unrooted:
        raise ProposalCompileError(
            ", ".join(sorted(unrooted))
            + " required deliverable(s) are not referenced by any acceptance "
            "criterion and therefore do not contribute to root verification"
        )

    # -- Constraints must not become work nodes ------------------------------
    for node in proposal.nodes:
        if node.kind == NodeKind.WORK and node.requirement_refs:
            refs = set(node.requirement_refs)
            constraint_refs = {
                r
                for r in refs
                if r in req_by_id
                and req_by_id[r].kind == RequirementKind.CONSTRAINT
            }
            if constraint_refs and refs == constraint_refs:
                raise ProposalCompileError(
                    f"node '{node.node_id}' has only constraint-kind "
                    f"requirement refs ({', '.join(sorted(constraint_refs))}); "
                    f"constraints must not become work nodes"
                )

    # -- Plan Mode forces read-only ------------------------------------------
    if proposal.interaction_mode == InteractionMode.PLAN:
        for node in proposal.nodes:
            if node.execution_mode != ExecutionMode.READ_ONLY:
                raise ProposalCompileError(
                    f"node '{node.node_id}' declares execution_mode "
                    f"'{node.execution_mode.value}' but interaction_mode is "
                    f"'plan'; all nodes must be read_only in plan mode"
                )

    # -- Validate and resolve paths ------------------------------------------
    for node in proposal.nodes:
        tag = f"node '{node.node_id}'"
        for p in node.allowed_paths:
            _validate_path_inside_repo(p, repo_resolved, f"{tag} allowed_paths")
        for p in node.context_packs:
            _validate_path_inside_repo(p, repo_resolved, f"{tag} context_packs")
        for p in node.write_paths:
            _validate_path_inside_repo(p, repo_resolved, f"{tag} write_paths")
        for p in node.artifact_inputs:
            _validate_path_inside_repo(
                p, repo_resolved, f"{tag} artifact_inputs"
            )

    # -- Execution mode / write scope consistency -----------------------------
    for node in proposal.nodes:
        if node.execution_mode == ExecutionMode.PATCH and not node.write_paths:
            raise ProposalCompileError(
                f"node '{node.node_id}' has execution_mode 'patch' "
                f"but no write_paths"
            )
        if node.write_paths and node.execution_mode == ExecutionMode.READ_ONLY:
            raise ProposalCompileError(
                f"node '{node.node_id}' declares write_paths but "
                f"execution_mode is 'read_only'"
            )

    # -- Build task contract graph -------------------------------------------
    graph = TaskContractGraph()
    for node in proposal.nodes:
        contract = _compile_node(node, repo_resolved)
        try:
            graph.add_node(contract)
        except ValueError as exc:
            raise ProposalCompileError(str(exc)) from exc

    for node in proposal.nodes:
        for dep in node.dependencies:
            try:
                graph.add_edge(GraphEdge(dep, node.node_id))
            except ValueError as exc:
                raise ProposalCompileError(
                    f"graph structure error for node '{node.node_id}' "
                    f"dependency '{dep}': {exc}"
                ) from exc

    # -- Shape ---------------------------------------------------------------
    shape = (
        ExecutionShape.FAST_PATH
        if len(proposal.nodes) == 1
        else ExecutionShape.GRAPH
    )

    # -- Build TaskSituation -------------------------------------------------
    task_id = f"proposal_{uuid4().hex[:12]}"
    requirements = RequirementLedger(
        items=[
            Requirement(
                id=r.id, text=r.text, kind=r.kind, required=r.required
            )
            for r in proposal.requirements
        ]
    )
    root_contract = RootContract(
        criteria=[
            AcceptanceCriterion(
                id=ac.id,
                description=ac.description,
                check=ac.check,
                requirement_refs=ac.requirement_refs,
            )
            for ac in proposal.acceptance_criteria
        ]
    )
    situation = TaskSituation(
        task_id=task_id,
        objective=proposal.root_goal,
        repo=repo_resolved,
        requirements=requirements,
        root_contract=root_contract,
        interaction_mode=proposal.interaction_mode,
        constraints=tuple(proposal.constraints),
        unresolved_questions=tuple(proposal.unresolved_questions),
        available_worker_ids=tuple(registry.workers.keys()),
    )

    # -- Assemble plan -------------------------------------------------------
    reasons: list[str] = []
    if shape == ExecutionShape.FAST_PATH:
        reasons.append("single proposal node compiled to fast path")
    else:
        reasons.append(
            f"{len(proposal.nodes)} proposal nodes compiled to task graph"
        )
    if proposal.interaction_mode == InteractionMode.PLAN:
        reasons.append("plan mode: all nodes forced to read-only")

    plan = DecompositionPlan(
        situation=situation,
        shape=shape,
        graph=graph,
        reasons=reasons,
    )

    # -- Worker assignment ---------------------------------------------------
    _assign_workers(plan, registry, worker_preferences, capability_profiles)

    # -- Final structural validation -----------------------------------------
    plan.validate()

    return plan


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _assign_workers(
    plan: DecompositionPlan,
    registry: WorkerRegistry,
    worker_preferences: dict[str, float] | None,
    capability_profiles: dict[str, object] | None,
) -> None:
    """Run hard-filter / soft-score assignment and attach risk manifests."""
    policy = WorkerAssignmentPolicy()
    prefs = worker_preferences or {}
    profiles = capability_profiles or {}

    for node in plan.graph.nodes.values():
        try:
            decision = policy.assign(
                node,
                registry,
                worker_preferences=prefs,
                capability_profiles=profiles,  # type: ignore[arg-type]
                verifier_available=node.verification.is_verifiable(),
            )
        except ValueError as exc:
            raise ProposalCompileError(
                f"worker assignment failed for node '{node.id}': {exc}"
            ) from exc

        node.assigned_worker_id = decision.worker_id
        record = decision.to_dict()
        worker = registry.get(decision.worker_id)
        record["risk_manifest"] = {
            "destination": f"{worker.harness}:{worker.model}",
            "privacy_zone": worker.capabilities.privacy_zone,
            "transmitted_paths": [
                str(path)
                for path in (*node.allowed_paths, *node.context_packs)
            ],
            "write_paths": [str(path) for path in node.write_paths],
            "execution_mode": node.execution_mode.value,
            "persistent_session": (
                node.hard_capabilities.persistent_session_required
            ),
            "callback": False,
            "consent_required": (
                worker.capabilities.privacy_zone == "approved_external"
            ),
        }
        plan.assignment_records[node.id] = record
        plan.reasons.append(
            f"{node.id} assigned to {node.assigned_worker_id} "
            f"after hard-capability filtering "
            f"(confidence={decision.confidence:.2f})"
        )


def _validate_path_inside_repo(
    path_str: str,
    repo_resolved: Path,
    context: str,
) -> None:
    """Raise ProposalCompileError if *path_str* resolves outside *repo_resolved*."""
    if not path_str or not path_str.strip():
        raise ProposalCompileError(f"{context}: empty path")
    p = Path(path_str)
    resolved = (repo_resolved / p) if not p.is_absolute() else p
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = resolved.absolute()
    repo_str = str(repo_resolved)
    if resolved != repo_resolved and not str(resolved).startswith(
        repo_str + os.sep
    ):
        raise ProposalCompileError(
            f"{context}: path '{path_str}' resolves outside repository "
            f"({resolved})"
        )


def _compile_node(node: ProposalNode, repo: Path) -> TaskNodeContract:
    """Compile a single :class:`ProposalNode` into a :class:`TaskNodeContract`."""
    hc = node.hard_capabilities

    hard_caps = HardCapabilityRequirements(
        modalities=frozenset(hc.get("modalities", ["text"])),
        tools=frozenset(hc.get("tools", [])),
        write_isolation=frozenset(hc.get("write_isolation", [])),
        network_required=hc.get("network_required", False),
        structured_output_required=hc.get("structured_output_required", False),
        min_context_tokens=hc.get("min_context_tokens", 0),
        persistent_session_required=hc.get(
            "persistent_session_required", False
        ),
        provider_protocols=frozenset(hc.get("provider_protocols", [])),
        privacy_zones=frozenset(hc.get("privacy_zones", [])),
    )

    vp = node.verifier_plan
    try:
        template_specs = validate_template_checks(
            vp.template_checks,
            execution_mode=node.execution_mode.value,
            write_paths=node.write_paths,
            repo_resolved=repo,
            root_contribution=vp.root_contribution or node.root_contribution,
            evidence_requirements=vp.evidence_requirements,
            semantic_criteria=vp.semantic_criteria,
        )
    except TemplateValidationError as exc:
        raise ProposalCompileError(
            f"invalid verifier plan for node '{node.node_id}': {exc}"
        ) from exc
    semantic_check = (
        "; ".join(vp.semantic_criteria) if vp.semantic_criteria else None
    )
    verification = VerificationContract(
        deterministic_checks=tuple(spec.to_string() for spec in template_specs),
        evidence_requirements=tuple(vp.evidence_requirements),
        semantic_check=semantic_check,
        root_contribution=vp.root_contribution or node.root_contribution,
    )

    def _resolve(p: str) -> Path:
        pp = Path(p)
        return pp if pp.is_absolute() else repo / pp

    return TaskNodeContract(
        id=node.node_id,
        objective=node.objective,
        kind=node.kind,
        requirement_refs=node.requirement_refs,
        context_packs=tuple(_resolve(p) for p in node.context_packs),
        artifact_inputs=node.artifact_inputs,
        allowed_paths=tuple(_resolve(p) for p in node.allowed_paths),
        write_paths=tuple(_resolve(p) for p in node.write_paths),
        output_type=node.output_type,
        execution_mode=node.execution_mode,
        hard_capabilities=hard_caps,
        soft_capabilities=dict(node.soft_capability_weights),
        verification=verification,
    )
