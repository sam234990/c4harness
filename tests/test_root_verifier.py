"""Tests for root-contract verification.

Covers:
* Full success -- all nodes done, all requirements covered, all criteria met.
* All nodes done but root unmet -- a required requirement is uncovered.
* Failed / blocked / inconclusive graph node -- graph rejected.
* Missing verification -- succeeded node has no VerificationResult.
* Uncovered requirement -- no accepted node covers a required requirement.
* Criterion traceability -- criteria traced to accepted node contributions.
* Semantic criterion inconclusive -- no explicit decision yields inconclusive.
* Semantic criterion explicit approval -- explicit decision accepts.
* Constraints -- constraint preserved and covered / not covered.
* Artifact conflict -- multiple accepted nodes claim same artifact.
* Empty graph -- no nodes, rejected as unhealthy.
* Serialization -- to_dict round-trip on all result types.
* Self-report detection -- accepted node without deterministic checks.
* Application facade -- verify_root delegates and calls hooks.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from c4harness.core.contracts import Evidence, VerificationResult
from c4harness.core.graph import (
    AcceptanceCriterion,
    DecompositionPlan,
    ExecutionShape,
    GraphEdge,
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
from c4harness.delegator.scheduler import (
    GraphResult,
    NodeOutcome,
    NodeState,
)
from c4harness.verifier.root import (
    CoverageReport,
    CriterionCoverage,
    RequirementCoverageEntry,
    RootVerificationResult,
    RootVerifier,
)
from c4harness.application.verify_root import verify_root
from c4harness.hooks import HookSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _req(
    rid: str,
    text: str = "",
    kind: RequirementKind = RequirementKind.DELIVERABLE,
    required: bool = True,
) -> Requirement:
    return Requirement(id=rid, text=text or f"text for {rid}", kind=kind, required=required)


def _criterion(
    cid: str,
    check: str = "semantic_review",
    requirement_refs: tuple[str, ...] = (),
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id=cid,
        description=f"desc for {cid}",
        check=check,
        requirement_refs=requirement_refs,
    )


def _node(
    nid: str,
    objective: str = "",
    kind: NodeKind = NodeKind.WORK,
    requirement_refs: tuple[str, ...] = (),
    deterministic_checks: tuple[str, ...] = ("file_exists:README.md",),
    evidence_requirements: tuple[str, ...] = (),
    semantic_check: str | None = None,
) -> TaskNodeContract:
    return TaskNodeContract(
        id=nid,
        objective=objective or f"obj for {nid}",
        kind=kind,
        requirement_refs=requirement_refs,
        verification=VerificationContract(
            deterministic_checks=deterministic_checks,
            evidence_requirements=evidence_requirements,
            semantic_check=semantic_check,
            root_contribution="; ".join(requirement_refs) if requirement_refs else "",
        ),
    )


def _make_plan(
    requirements: list[Requirement],
    criteria: list[AcceptanceCriterion],
    nodes: list[TaskNodeContract],
    edges: list[GraphEdge] | None = None,
) -> DecompositionPlan:
    graph = TaskContractGraph()
    for n in nodes:
        graph.add_node(n)
    for e in edges or []:
        graph.add_edge(e)
    situation = TaskSituation(
        task_id="test-task",
        objective="test objective",
        repo=Path("/tmp/test"),
        requirements=RequirementLedger(items=requirements),
        root_contract=RootContract(criteria=criteria),
    )
    return DecompositionPlan(
        situation=situation,
        shape=ExecutionShape.GRAPH if edges else ExecutionShape.FAST_PATH,
        graph=graph,
    )


def _make_graph_result(
    outcomes: dict[str, NodeState],
    execution_order: list[str] | None = None,
) -> GraphResult:
    node_outcomes = {
        nid: NodeOutcome(node_id=nid, state=state)
        for nid, state in outcomes.items()
    }
    return GraphResult(
        node_outcomes=node_outcomes,
        execution_order=execution_order or list(outcomes.keys()),
    )


def _vr(accepted: bool = True, confidence: str = "high") -> VerificationResult:
    return VerificationResult(accepted=accepted, confidence=confidence)


# ---------------------------------------------------------------------------
# Full success
# ---------------------------------------------------------------------------


class TestFullSuccess(unittest.TestCase):
    """All nodes succeeded, all verifications accepted, everything covered."""

    def test_full_success_accepted(self) -> None:
        req_a = _req("r1")
        crit = _criterion("c1", check="file_exists:output.txt", requirement_refs=("r1",))
        node_a = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req_a], [crit], [node_a])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.issues, [])
        self.assertTrue(len(result.memory_facts) > 0)

    def test_full_success_multi_node(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r2",))
        plan = _make_plan([req1, req2], [crit], [n1, n2])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED, "n2": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(), "n2": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        self.assertEqual(result.confidence, "high")


# ---------------------------------------------------------------------------
# All nodes done but root unmet
# ---------------------------------------------------------------------------


class TestAllNodesDoneButRootUnmet(unittest.TestCase):
    """Nodes succeeded but a required requirement is not covered."""

    def test_uncovered_required_requirement(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        # Only n1 covers r1; r2 is uncovered.
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1, req2], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "low")
        self.assertTrue(any("r2" in iss for iss in result.issues))


# ---------------------------------------------------------------------------
# Failed / blocked / inconclusive graph node
# ---------------------------------------------------------------------------


class TestFailedBlockedInconclusiveNode(unittest.TestCase):
    """Graph with failures / blocked nodes is always rejected."""

    def test_failed_node_rejects(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.FAILED})
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "blocked")
        self.assertTrue(any("failed" in iss.lower() for iss in result.issues))

    def test_blocked_node_rejects(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r1",))
        plan = _make_plan(
            [req1], [crit], [n1, n2],
            edges=[GraphEdge(source="n1", target="n2")],
        )
        gr = _make_graph_result({
            "n1": NodeState.FAILED,
            "n2": NodeState.BLOCKED,
        })
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "blocked")

    def test_deadlock_rejects(self) -> None:
        """Deadlock (terminal, no failures, not all_succeeded) is rejected."""
        req1 = _req("r1")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        # Construct a GraphResult that looks like a deadlock.
        gr = GraphResult(
            node_outcomes={
                "n1": NodeOutcome(node_id="n1", state=NodeState.BLOCKED),
            },
            execution_order=[],
        )
        # deadlock_detected: terminal, not all_succeeded, no failures
        self.assertTrue(gr.deadlock_detected)

        verifications: dict[str, VerificationResult] = {}
        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "blocked")
        self.assertTrue(any("deadlock" in iss.lower() for iss in result.issues))


# ---------------------------------------------------------------------------
# Missing verification
# ---------------------------------------------------------------------------


class TestMissingVerification(unittest.TestCase):
    """Succeeded node without a VerificationResult is detected."""

    def test_missing_verification_detected(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        # No verification for n1.
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertTrue(any("n1" in iss for iss in result.issues))
        self.assertTrue(any("missing" in iss.lower() for iss in result.issues))


# ---------------------------------------------------------------------------
# Uncovered requirement
# ---------------------------------------------------------------------------


class TestUncoveredRequirement(unittest.TestCase):
    """Required requirement with no accepted covering node is flagged."""

    def test_verification_rejected_means_not_covered(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        # Verification rejected → n1 not in accepted_nodes.
        verifications = {"n1": _vr(accepted=False)}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertTrue(any("r1" in iss for iss in result.issues))

    def test_optional_requirement_uncovered_is_not_fatal(self) -> None:
        req1 = _req("r1", required=False)
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.FAILED})
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        # Graph failure already rejects.
        self.assertFalse(result.accepted)


# ---------------------------------------------------------------------------
# Criterion traceability
# ---------------------------------------------------------------------------


class TestCriterionTraceability(unittest.TestCase):
    """Criteria's requirement_refs trace to accepted node contributions."""

    def test_deterministic_criterion_covered(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r2",))
        plan = _make_plan([req1, req2], [crit], [n1, n2])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED, "n2": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(), "n2": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "covered")
        self.assertIn("n1", c1_cov.contributing_nodes)
        self.assertIn("n2", c1_cov.contributing_nodes)

    def test_deterministic_criterion_uncovered_ref(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1, req2], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "uncovered")
        self.assertIn("r2", c1_cov.uncovered_requirement_refs)

    def test_criterion_with_no_refs_covered_by_any_accepted(self) -> None:
        """Criterion with no requirement_refs is covered if accepted nodes exist."""
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=())
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "covered")


# ---------------------------------------------------------------------------
# Semantic criterion: inconclusive without explicit decision
# ---------------------------------------------------------------------------


class TestSemanticCriterionInconclusive(unittest.TestCase):
    """Semantic criteria are inconclusive without explicit decision."""

    def test_semantic_review_inconclusive(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "inconclusive")
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "inconclusive")
        self.assertTrue(any("auto-pass" in iss.lower() or "explicit" in iss.lower()
                            for iss in c1_cov.issues))

    def test_unknown_check_type_also_inconclusive(self) -> None:
        """Any non-deterministic check name is treated as semantic."""
        req1 = _req("r1")
        crit = _criterion("c1", check="custom_quality_check", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "inconclusive")


# ---------------------------------------------------------------------------
# Semantic criterion: explicit approval
# ---------------------------------------------------------------------------


class TestSemanticCriterionExplicitApproval(unittest.TestCase):
    """Semantic criteria with explicit decision are accepted/rejected."""

    def test_explicit_approval_accepted(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(
            plan, gr, verifications, explicit_decisions={"c1": True}
        )
        self.assertTrue(result.accepted)
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "covered")

    def test_explicit_rejection_rejected(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(
            plan, gr, verifications, explicit_decisions={"c1": False}
        )
        self.assertFalse(result.accepted)
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "uncovered")


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


class TestConstraints(unittest.TestCase):
    """Constraint-kind requirements preserved as root-level conditions."""

    def test_constraint_covered_passes(self) -> None:
        req_c = _req("c1", kind=RequirementKind.CONSTRAINT)
        req_d = _req("r1")
        crit = _criterion("crit1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1", "c1"))
        plan = _make_plan([req_c, req_d], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        self.assertEqual(result.coverage_report.constraint_preservation, [])

    def test_constraint_not_covered_fails(self) -> None:
        req_c = _req("c1", kind=RequirementKind.CONSTRAINT)
        req_d = _req("r1")
        crit = _criterion("crit1", check="file_exists:out.txt", requirement_refs=("r1",))
        # n1 covers r1 but not the constraint c1.
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req_c, req_d], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any("c1" in iss and "constraint" in iss.lower()
                for iss in result.issues)
        )


# ---------------------------------------------------------------------------
# Artifact conflict
# ---------------------------------------------------------------------------


class TestArtifactConflict(unittest.TestCase):
    """Multiple accepted nodes claiming same artifact path is detected."""

    def test_artifact_conflict_detected(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r2",))
        plan = _make_plan([req1, req2], [crit], [n1, n2])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED, "n2": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(), "n2": _vr()}
        evidence = {
            "n1": [Evidence(path="src/main.py", observation="created")],
            "n2": [Evidence(path="src/main.py", observation="modified")],
        }

        result = RootVerifier().verify(
            plan, gr, verifications, node_evidence=evidence
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("conflict" in iss.lower() for iss in result.issues))
        self.assertEqual(len(result.coverage_report.artifact_conflicts), 1)

    def test_no_conflict_different_paths(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r2",))
        plan = _make_plan([req1, req2], [crit], [n1, n2])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED, "n2": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(), "n2": _vr()}
        evidence = {
            "n1": [Evidence(path="src/a.py", observation="ok")],
            "n2": [Evidence(path="src/b.py", observation="ok")],
        }

        result = RootVerifier().verify(
            plan, gr, verifications, node_evidence=evidence
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.coverage_report.artifact_conflicts, [])


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph(unittest.TestCase):
    """An empty graph has no nodes to cover requirements."""

    def test_empty_graph_no_requirements(self) -> None:
        """Empty graph with no requirements -- still rejected because nothing covered."""
        plan = DecompositionPlan(
            situation=TaskSituation(
                task_id="t",
                objective="obj",
                repo=Path("/tmp"),
                requirements=RequirementLedger(items=[]),
                root_contract=RootContract(criteria=[_criterion("c1")]),
            ),
            shape=ExecutionShape.FAST_PATH,
            graph=TaskContractGraph(),
        )
        gr = GraphResult(node_outcomes={}, execution_order=[])
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        # No nodes means the semantic criterion has no accepted nodes.
        c1_cov = result.coverage_report.criterion_coverage[0]
        self.assertEqual(c1_cov.status, "inconclusive")

    def test_empty_graph_with_requirement_uncovered(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [])
        gr = GraphResult(node_outcomes={}, execution_order=[])
        verifications: dict[str, VerificationResult] = {}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertTrue(any("r1" in iss for iss in result.issues))


# ---------------------------------------------------------------------------
# Self-report detection
# ---------------------------------------------------------------------------


class TestSelfReportDetection(unittest.TestCase):
    """Accepted node without deterministic checks is flagged as self-report."""

    def test_node_without_checks_flagged(self) -> None:
        req1 = _req("r1")
        # Semantic-only check on the criterion so it can be explicitly approved.
        crit = _criterion("c1", check="semantic_review", requirement_refs=("r1",))
        # Node has only semantic_check -- no deterministic checks or evidence.
        n1 = _node(
            "n1",
            requirement_refs=("r1",),
            deterministic_checks=(),
            evidence_requirements=(),
            semantic_check="Code is clean",
        )
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        # Node-level verification accepted (e.g. by explicit orchestrator).
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(
            plan, gr, verifications, explicit_decisions={"c1": True}
        )
        # An explicit root decision cannot turn an unverified worker claim
        # into accepted evidence.
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "inconclusive")
        self.assertTrue(len(result.coverage_report.self_report_only_claims) > 0)
        self.assertTrue(any("n1" in c for c in result.coverage_report.self_report_only_claims))

    def test_node_with_checks_not_flagged(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node(
            "n1",
            requirement_refs=("r1",),
            deterministic_checks=("file_exists:out.txt",),
        )
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.coverage_report.self_report_only_claims, [])


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization(unittest.TestCase):
    """to_dict round-trip on all result types."""

    def test_root_verification_result_to_dict(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        d = result.to_dict()

        self.assertIn("accepted", d)
        self.assertIn("confidence", d)
        self.assertIn("issues", d)
        self.assertIn("memory_facts", d)
        self.assertIn("coverage_report", d)

        cr = d["coverage_report"]
        self.assertIn("requirement_coverage", cr)
        self.assertIn("criterion_coverage", cr)
        self.assertIn("constraint_preservation", cr)
        self.assertIn("artifact_conflicts", cr)
        self.assertIn("self_report_only_claims", cr)

        # Check nested structures are serializable.
        self.assertIsInstance(cr["requirement_coverage"], list)
        if cr["requirement_coverage"]:
            entry = cr["requirement_coverage"][0]
            self.assertIn("requirement_id", entry)
            self.assertIn("covered", entry)
            self.assertIsInstance(entry["covering_nodes"], list)

        if cr["criterion_coverage"]:
            entry = cr["criterion_coverage"][0]
            self.assertIn("criterion_id", entry)
            self.assertIn("status", entry)
            self.assertIsInstance(entry["contributing_nodes"], list)

    def test_requirement_coverage_entry_to_dict(self) -> None:
        entry = RequirementCoverageEntry(
            requirement_id="r1",
            required=True,
            kind="deliverable",
            covered=True,
            covering_nodes=("n1",),
            accepted_covering_nodes=("n1",),
        )
        d = entry.to_dict()
        self.assertEqual(d["requirement_id"], "r1")
        self.assertTrue(d["covered"])
        self.assertEqual(d["covering_nodes"], ["n1"])

    def test_criterion_coverage_to_dict(self) -> None:
        entry = CriterionCoverage(
            criterion_id="c1",
            description="desc",
            check="tests_pass",
            status="covered",
            contributing_nodes=("n1",),
            uncovered_requirement_refs=(),
            issues=(),
        )
        d = entry.to_dict()
        self.assertEqual(d["criterion_id"], "c1")
        self.assertEqual(d["status"], "covered")
        self.assertEqual(d["contributing_nodes"], ["n1"])
        self.assertEqual(d["issues"], [])

    def test_coverage_report_to_dict(self) -> None:
        report = CoverageReport(
            requirement_coverage=[],
            criterion_coverage=[],
            constraint_preservation=["ok"],
            artifact_conflicts=[],
            self_report_only_claims=[],
        )
        d = report.to_dict()
        self.assertEqual(d["constraint_preservation"], ["ok"])

    def test_dict_is_json_compatible(self) -> None:
        """Ensure the entire result dict can be serialized to JSON."""
        import json

        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        # Should not raise.
        json_str = json.dumps(result.to_dict())
        parsed = json.loads(json_str)
        self.assertTrue(parsed["accepted"])


# ---------------------------------------------------------------------------
# Application facade
# ---------------------------------------------------------------------------


class TestVerifyRootFacade(unittest.TestCase):
    """verify_root delegates to RootVerifier and calls hooks."""

    def test_facade_returns_root_verification_result(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = verify_root(plan, gr, verifications)
        self.assertIsInstance(result, RootVerificationResult)
        self.assertTrue(result.accepted)

    def test_facade_calls_post_root_verify_hook(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        hook_calls: list[tuple[Any, Any]] = []

        class CapturingHooks(HookSet):
            def post_root_verify(self, plan: Any, verification: VerificationResult) -> None:
                hook_calls.append((plan, verification))

        hooks = CapturingHooks()
        result = verify_root(plan, gr, verifications, hooks=hooks)

        self.assertEqual(len(hook_calls), 1)
        hook_plan, hook_vr = hook_calls[0]
        self.assertIs(hook_plan, plan)
        self.assertIsInstance(hook_vr, VerificationResult)
        self.assertEqual(hook_vr.accepted, result.accepted)
        self.assertEqual(hook_vr.confidence, result.confidence)

    def test_facade_passes_explicit_decisions(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = verify_root(
            plan, gr, verifications, explicit_decisions={"c1": True}
        )
        self.assertTrue(result.accepted)

    def test_facade_passes_node_evidence(self) -> None:
        req1 = _req("r1")
        req2 = _req("r2")
        crit = _criterion("c1", check="tests_pass", requirement_refs=("r1", "r2"))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r2",))
        plan = _make_plan([req1, req2], [crit], [n1, n2])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED, "n2": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(), "n2": _vr()}
        evidence = {
            "n1": [Evidence(path="same.py", observation="a")],
            "n2": [Evidence(path="same.py", observation="b")],
        }

        result = verify_root(plan, gr, verifications, node_evidence=evidence)
        self.assertFalse(result.accepted)
        self.assertTrue(any("conflict" in iss.lower() for iss in result.issues))

    def test_facade_no_hooks_no_error(self) -> None:
        """verify_root works without a hooks argument."""
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = verify_root(plan, gr, verifications, hooks=None)
        self.assertTrue(result.accepted)


# ---------------------------------------------------------------------------
# Edge cases: multiple criteria, mixed deterministic/semantic
# ---------------------------------------------------------------------------


class TestMixedCriteria(unittest.TestCase):
    """Plan with both deterministic and semantic criteria."""

    def test_one_deterministic_pass_one_semantic_inconclusive(self) -> None:
        req1 = _req("r1")
        crit_det = _criterion("c_det", check="file_exists:out.txt", requirement_refs=("r1",))
        crit_sem = _criterion("c_sem", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit_det, crit_sem], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence, "inconclusive")
        # c_det is covered, c_sem is inconclusive.
        statuses = {c.criterion_id: c.status for c in result.coverage_report.criterion_coverage}
        self.assertEqual(statuses["c_det"], "covered")
        self.assertEqual(statuses["c_sem"], "inconclusive")

    def test_both_pass_when_semantic_approved(self) -> None:
        req1 = _req("r1")
        crit_det = _criterion("c_det", check="file_exists:out.txt", requirement_refs=("r1",))
        crit_sem = _criterion("c_sem", check="semantic_review", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit_det, crit_sem], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr()}

        result = RootVerifier().verify(
            plan, gr, verifications, explicit_decisions={"c_sem": True}
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.confidence, "high")


# ---------------------------------------------------------------------------
# Node-level verification rejected but graph succeeded
# ---------------------------------------------------------------------------


class TestNodeVerificationRejected(unittest.TestCase):
    """Node succeeded but verification rejected -- not in accepted set."""

    def test_rejected_node_not_accepted(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1])
        gr = _make_graph_result({"n1": NodeState.SUCCEEDED})
        verifications = {"n1": _vr(accepted=False, confidence="low")}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertFalse(result.accepted)
        # Coverage report shows n1 covers r1 but is not accepted.
        req_cov = result.coverage_report.requirement_coverage[0]
        self.assertIn("n1", req_cov.covering_nodes)
        self.assertEqual(req_cov.accepted_covering_nodes, ())
        self.assertFalse(req_cov.covered)


# ---------------------------------------------------------------------------
# Multiple nodes covering same requirement
# ---------------------------------------------------------------------------


class TestMultipleCoveringNodes(unittest.TestCase):
    """Requirement covered by multiple nodes -- one accepted is enough."""

    def test_one_of_two_accepted_suffices(self) -> None:
        req1 = _req("r1")
        crit = _criterion("c1", check="file_exists:out.txt", requirement_refs=("r1",))
        n1 = _node("n1", requirement_refs=("r1",))
        n2 = _node("n2", requirement_refs=("r1",))
        plan = _make_plan([req1], [crit], [n1, n2])
        gr = _make_graph_result({
            "n1": NodeState.SUCCEEDED,
            "n2": NodeState.SUCCEEDED,
        })
        # n1 accepted, n2 rejected.
        verifications = {"n1": _vr(), "n2": _vr(accepted=False)}

        result = RootVerifier().verify(plan, gr, verifications)
        self.assertTrue(result.accepted)
        req_cov = result.coverage_report.requirement_coverage[0]
        self.assertIn("n1", req_cov.accepted_covering_nodes)
        self.assertNotIn("n2", req_cov.accepted_covering_nodes)
        self.assertTrue(req_cov.covered)


if __name__ == "__main__":
    unittest.main()
