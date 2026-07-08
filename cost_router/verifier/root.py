"""Deterministic root verifier for DecompositionPlan verification.

The root verifier consumes a :class:`DecompositionPlan`
(:class:`TaskSituation`, :class:`RequirementLedger`, :class:`RootContract`,
:class:`TaskContractGraph`), :class:`GraphResult` with node terminal states,
and per-node :class:`VerificationResult` plus inspectable evidence references.
It produces a :class:`RootVerificationResult` that encodes
acceptance/rejection/inconclusive semantics along with a serializable
:class:`CoverageReport`.

Design guarantees
=================
* Graph failures, blocked, or incomplete states are **always rejected**.
* Every required requirement must be covered by at least one accepted node.
* Every ``RootContract`` criterion's ``requirement_refs`` must trace to
  accepted node contributions.
* Constraints are preserved as root-level conditions, not work nodes.
* Missing node verification is detected and rejected.
* Conflicting/duplicate artifact ownership is detected when evidence is
  supplied.
* Claims supported only by worker self-report (no deterministic checks) are
  flagged.
* Semantic / non-deterministic criteria are *inconclusive* unless an explicit
  orchestrator/reviewer decision is supplied -- they never auto-pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.contracts import Evidence, VerificationResult
from ..core.graph import (
    AcceptanceCriterion,
    DecompositionPlan,
    RequirementLedger,
    RootContract,
    TaskContractGraph,
)
from ..delegator.scheduler import GraphResult, NodeState


# ---------------------------------------------------------------------------
# Coverage report data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequirementCoverageEntry:
    """Coverage status for a single requirement."""

    requirement_id: str
    required: bool
    kind: str
    covered: bool
    covering_nodes: tuple[str, ...]
    accepted_covering_nodes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "required": self.required,
            "kind": self.kind,
            "covered": self.covered,
            "covering_nodes": list(self.covering_nodes),
            "accepted_covering_nodes": list(self.accepted_covering_nodes),
        }


@dataclass(frozen=True, slots=True)
class CriterionCoverage:
    """Coverage status for a single acceptance criterion."""

    criterion_id: str
    description: str
    check: str
    status: str  # "covered", "uncovered", "inconclusive"
    contributing_nodes: tuple[str, ...]
    uncovered_requirement_refs: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "check": self.check,
            "status": self.status,
            "contributing_nodes": list(self.contributing_nodes),
            "uncovered_requirement_refs": list(self.uncovered_requirement_refs),
            "issues": list(self.issues),
        }


@dataclass(slots=True)
class CoverageReport:
    """Serializable report of requirement and criterion coverage."""

    requirement_coverage: list[RequirementCoverageEntry] = field(
        default_factory=list
    )
    criterion_coverage: list[CriterionCoverage] = field(default_factory=list)
    constraint_preservation: list[str] = field(default_factory=list)
    artifact_conflicts: list[str] = field(default_factory=list)
    self_report_only_claims: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_coverage": [e.to_dict() for e in self.requirement_coverage],
            "criterion_coverage": [c.to_dict() for c in self.criterion_coverage],
            "constraint_preservation": list(self.constraint_preservation),
            "artifact_conflicts": list(self.artifact_conflicts),
            "self_report_only_claims": list(self.self_report_only_claims),
        }


# ---------------------------------------------------------------------------
# Root verification result (compatible wrapper around VerificationResult)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RootVerificationResult:
    """Root-level verification outcome with serializable coverage report.

    Carries the same core fields as :class:`VerificationResult`
    (``accepted``, ``confidence``, ``issues``, ``memory_facts``) plus a
    :class:`CoverageReport` for full traceability.
    """

    accepted: bool
    confidence: str
    issues: list[str] = field(default_factory=list)
    memory_facts: list[str] = field(default_factory=list)
    coverage_report: CoverageReport = field(default_factory=CoverageReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "confidence": self.confidence,
            "issues": list(self.issues),
            "memory_facts": list(self.memory_facts),
            "coverage_report": self.coverage_report.to_dict(),
        }


# ---------------------------------------------------------------------------
# Known deterministic template check names
# ---------------------------------------------------------------------------

_DETERMINISTIC_CHECK_NAMES: frozenset[str] = frozenset({
    "file_exists",
    "file_contains",
    "command_exit_zero",
    "output_matches",
    "tests_pass",
    "json_schema_valid",
    "changed_paths_within_allowlist",
    "patch_non_empty",
    "requirement_coverage",
})


# ---------------------------------------------------------------------------
# RootVerifier
# ---------------------------------------------------------------------------


class RootVerifier:
    """Deterministic root verifier for :class:`DecompositionPlan`.

    The verifier does **not** select workers, write shared memory, or invoke
    any backend.  It only inspects the plan, graph result, and per-node
    verification outcomes.
    """

    # -- public API ----------------------------------------------------------

    def verify(
        self,
        plan: DecompositionPlan,
        graph_result: GraphResult,
        node_verifications: dict[str, VerificationResult],
        node_evidence: dict[str, list[Evidence]] | None = None,
        explicit_decisions: dict[str, bool] | None = None,
    ) -> RootVerificationResult:
        """Run root verification and return a structured result.

        Parameters
        ----------
        plan:
            The compiled decomposition plan.
        graph_result:
            Inspectable result of graph execution (node terminal states).
        node_verifications:
            Per-node verification outcomes keyed by ``node_id``.
        node_evidence:
            Per-node evidence references keyed by ``node_id``.  Used for
            artifact-conflict detection.
        explicit_decisions:
            Orchestrator/reviewer decisions for semantic criteria, keyed by
            ``criterion_id``.  ``True`` = approved, ``False`` = rejected.

        Returns
        -------
        RootVerificationResult
        """
        node_evidence = node_evidence or {}
        explicit_decisions = explicit_decisions or {}
        issues: list[str] = []
        facts: list[str] = []

        # ------------------------------------------------------------------
        # 1. Reject graph failures / blocked / incomplete states
        # ------------------------------------------------------------------
        graph_issues = self._check_graph_health(graph_result)
        if graph_issues:
            return RootVerificationResult(
                accepted=False,
                confidence="blocked",
                issues=graph_issues,
                memory_facts=facts,
                coverage_report=CoverageReport(),
            )

        situation = plan.situation
        graph = plan.graph

        # ------------------------------------------------------------------
        # 2. Detect missing node verification
        # ------------------------------------------------------------------
        missing_verification = self._find_missing_verifications(
            graph_result, node_verifications
        )
        if missing_verification:
            issues.append(
                "Missing verification for succeeded nodes: "
                + ", ".join(missing_verification)
            )

        # ------------------------------------------------------------------
        # 3. Build accepted-node set
        # ------------------------------------------------------------------
        accepted_nodes = self._compute_accepted_nodes(
            graph_result, node_verifications
        )

        # ------------------------------------------------------------------
        # 4. Requirement coverage
        # ------------------------------------------------------------------
        requirement_entries = self._check_requirement_coverage(
            situation.requirements, graph, accepted_nodes
        )

        # ------------------------------------------------------------------
        # 5. Criterion traceability
        # ------------------------------------------------------------------
        criterion_entries = self._check_criterion_traceability(
            situation.root_contract,
            graph,
            accepted_nodes,
            explicit_decisions,
        )

        # ------------------------------------------------------------------
        # 6. Constraint preservation
        # ------------------------------------------------------------------
        constraint_issues = self._check_constraints(
            situation.requirements, graph, accepted_nodes
        )

        # ------------------------------------------------------------------
        # 7. Artifact conflict detection
        # ------------------------------------------------------------------
        artifact_conflicts = self._detect_artifact_conflicts(
            node_evidence, accepted_nodes
        )

        # ------------------------------------------------------------------
        # 8. Self-report-only claim detection
        # ------------------------------------------------------------------
        self_report_claims = self._detect_self_report_claims(
            graph, accepted_nodes
        )

        # ------------------------------------------------------------------
        # 9. Assemble coverage report
        # ------------------------------------------------------------------
        coverage = CoverageReport(
            requirement_coverage=requirement_entries,
            criterion_coverage=criterion_entries,
            constraint_preservation=constraint_issues,
            artifact_conflicts=artifact_conflicts,
            self_report_only_claims=self_report_claims,
        )

        # ------------------------------------------------------------------
        # 10. Determine overall acceptance
        # ------------------------------------------------------------------
        uncovered_required = [
            e.requirement_id
            for e in requirement_entries
            if e.required and not e.covered
        ]
        uncovered_criteria = [
            c.criterion_id for c in criterion_entries if c.status == "uncovered"
        ]
        inconclusive_criteria = [
            c.criterion_id
            for c in criterion_entries
            if c.status == "inconclusive"
        ]

        if uncovered_required:
            issues.append(
                "Required requirements not covered by accepted nodes: "
                + ", ".join(sorted(uncovered_required))
            )

        if uncovered_criteria:
            issues.append(
                "Root contract criteria not covered: "
                + ", ".join(sorted(uncovered_criteria))
            )

        if artifact_conflicts:
            issues.append(
                "Artifact conflicts detected: " + "; ".join(artifact_conflicts)
            )

        if constraint_issues:
            issues.extend(constraint_issues)

        # Confidence and acceptance
        if issues:
            accepted = False
            confidence = "low"
        elif inconclusive_criteria:
            accepted = False
            confidence = "inconclusive"
            issues.append(
                "Inconclusive semantic criteria require explicit decision: "
                + ", ".join(sorted(inconclusive_criteria))
            )
        elif self_report_claims:
            accepted = False
            confidence = "inconclusive"
            issues.append(
                "Some claims rely only on worker self-report and require reviewer evidence."
            )
        else:
            accepted = True
            confidence = "high"
            facts.append(
                "All requirements covered by accepted nodes with verified evidence."
            )
            facts.append(
                "All root contract criteria traced to accepted node contributions."
            )

        return RootVerificationResult(
            accepted=accepted,
            confidence=confidence,
            issues=issues,
            memory_facts=facts,
            coverage_report=coverage,
        )

    # -- internal checks -----------------------------------------------------

    @staticmethod
    def _check_graph_health(graph_result: GraphResult) -> list[str]:
        """Return issues if the graph is unhealthy; empty list otherwise."""
        issues: list[str] = []
        if graph_result.has_failures:
            issues.append(
                "Graph has failed nodes; root verification rejected."
            )
        if graph_result.is_incomplete:
            issues.append(
                "Graph is incomplete with blocked nodes; root verification rejected."
            )
        if graph_result.deadlock_detected:
            issues.append(
                "Graph deadlock detected; root verification rejected."
            )
        return issues

    @staticmethod
    def _find_missing_verifications(
        graph_result: GraphResult,
        node_verifications: dict[str, VerificationResult],
    ) -> list[str]:
        """Return ids of succeeded nodes that have no verification result."""
        return sorted(
            nid
            for nid, outcome in graph_result.node_outcomes.items()
            if outcome.state == NodeState.SUCCEEDED
            and nid not in node_verifications
        )

    @staticmethod
    def _compute_accepted_nodes(
        graph_result: GraphResult,
        node_verifications: dict[str, VerificationResult],
    ) -> set[str]:
        """Return node ids that are both succeeded and verified accepted."""
        accepted: set[str] = set()
        for nid, vr in node_verifications.items():
            outcome = graph_result.node_outcomes.get(nid)
            if (
                outcome is not None
                and outcome.state == NodeState.SUCCEEDED
                and vr.accepted
            ):
                accepted.add(nid)
        return accepted

    @staticmethod
    def _check_requirement_coverage(
        ledger: RequirementLedger,
        graph: TaskContractGraph,
        accepted_nodes: set[str],
    ) -> list[RequirementCoverageEntry]:
        entries: list[RequirementCoverageEntry] = []
        for req in ledger.items:
            covering = sorted(
                nid
                for nid, node in graph.nodes.items()
                if req.id in node.requirement_refs
            )
            accepted_covering = sorted(
                nid for nid in covering if nid in accepted_nodes
            )
            entries.append(
                RequirementCoverageEntry(
                    requirement_id=req.id,
                    required=req.required,
                    kind=req.kind.value,
                    covered=bool(accepted_covering),
                    covering_nodes=tuple(covering),
                    accepted_covering_nodes=tuple(accepted_covering),
                )
            )
        return entries

    def _check_criterion_traceability(
        self,
        root_contract: RootContract,
        graph: TaskContractGraph,
        accepted_nodes: set[str],
        explicit_decisions: dict[str, bool],
    ) -> list[CriterionCoverage]:
        entries: list[CriterionCoverage] = []
        for criterion in root_contract.criteria:
            is_semantic = self._is_semantic_check(criterion.check)

            if is_semantic:
                status, contributing, uncovered_refs, crit_issues = (
                    self._evaluate_semantic_criterion(
                        criterion, accepted_nodes, explicit_decisions
                    )
                )
            else:
                status, contributing, uncovered_refs, crit_issues = (
                    self._evaluate_deterministic_criterion(
                        criterion, graph, accepted_nodes
                    )
                )

            entries.append(
                CriterionCoverage(
                    criterion_id=criterion.id,
                    description=criterion.description,
                    check=criterion.check,
                    status=status,
                    contributing_nodes=tuple(contributing),
                    uncovered_requirement_refs=tuple(uncovered_refs),
                    issues=tuple(crit_issues),
                )
            )
        return entries

    @staticmethod
    def _is_semantic_check(check: str) -> bool:
        """Return True if the check is non-deterministic / semantic."""
        template_name = check.split(":")[0]
        return template_name not in _DETERMINISTIC_CHECK_NAMES

    @staticmethod
    def _evaluate_semantic_criterion(
        criterion: AcceptanceCriterion,
        accepted_nodes: set[str],
        explicit_decisions: dict[str, bool],
    ) -> tuple[str, list[str], list[str], list[str]]:
        """Return (status, contributing_nodes, uncovered_refs, issues)."""
        if criterion.id in explicit_decisions:
            decision = explicit_decisions[criterion.id]
            if decision:
                return (
                    "covered",
                    sorted(accepted_nodes),
                    [],
                    [],
                )
            return (
                "uncovered",
                [],
                [],
                ["Explicitly rejected by orchestrator decision."],
            )
        return (
            "inconclusive",
            [],
            [],
            [
                "Semantic criterion requires explicit orchestrator/reviewer "
                "decision; auto-pass is not permitted."
            ],
        )

    @staticmethod
    def _evaluate_deterministic_criterion(
        criterion: AcceptanceCriterion,
        graph: TaskContractGraph,
        accepted_nodes: set[str],
    ) -> tuple[str, list[str], list[str], list[str]]:
        """Return (status, contributing_nodes, uncovered_refs, issues)."""
        contributing_set: set[str] = set()
        uncovered_refs: list[str] = []

        for ref in criterion.requirement_refs:
            covering = sorted(
                nid
                for nid, node in graph.nodes.items()
                if ref in node.requirement_refs and nid in accepted_nodes
            )
            if covering:
                contributing_set.update(covering)
            else:
                uncovered_refs.append(ref)

        contributing = sorted(contributing_set)

        if uncovered_refs:
            return (
                "uncovered",
                contributing,
                sorted(uncovered_refs),
                [
                    "Uncovered requirement refs: "
                    + ", ".join(sorted(uncovered_refs))
                ],
            )

        if not criterion.requirement_refs and not accepted_nodes:
            return (
                "uncovered",
                [],
                [],
                [
                    "No accepted nodes to cover criterion "
                    "without requirement_refs."
                ],
            )

        return ("covered", contributing, [], [])

    @staticmethod
    def _check_constraints(
        ledger: RequirementLedger,
        graph: TaskContractGraph,
        accepted_nodes: set[str],
    ) -> list[str]:
        issues: list[str] = []
        for req in ledger.items:
            if req.kind.value != "constraint":
                continue
            covering_accepted = [
                nid
                for nid, node in graph.nodes.items()
                if req.id in node.requirement_refs and nid in accepted_nodes
            ]
            if not covering_accepted:
                issues.append(
                    f"Constraint '{req.id}' not covered by any accepted node."
                )
        return issues

    @staticmethod
    def _detect_artifact_conflicts(
        node_evidence: dict[str, list[Evidence]],
        accepted_nodes: set[str],
    ) -> list[str]:
        path_owners: dict[str, list[str]] = {}
        for nid in accepted_nodes:
            for ev in node_evidence.get(nid, []):
                if ev.path:
                    path_owners.setdefault(ev.path, []).append(nid)

        conflicts: list[str] = []
        for path in sorted(path_owners):
            owners = sorted(set(path_owners[path]))
            if len(owners) > 1:
                conflicts.append(
                    f"Artifact '{path}' claimed by multiple accepted nodes: "
                    + ", ".join(owners)
                )
        return conflicts

    @staticmethod
    def _detect_self_report_claims(
        graph: TaskContractGraph,
        accepted_nodes: set[str],
    ) -> list[str]:
        claims: list[str] = []
        for nid in sorted(accepted_nodes):
            node = graph.nodes.get(nid)
            if node is None:
                continue
            verification = node.verification
            if (
                not verification.deterministic_checks
                and not verification.evidence_requirements
            ):
                claims.append(
                    f"Node '{nid}' accepted without deterministic checks or "
                    "evidence requirements; relies on worker self-report."
                )
        return claims
