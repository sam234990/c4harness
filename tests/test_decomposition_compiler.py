"""Tests for deterministic task proposal compilation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from c4harness.decompose import (
    ExecutionMode,
    ExecutionShape,
    InteractionMode,
    NodeKind,
    RequirementKind,
    WorkerArm,
    WorkerCapabilities,
    WorkerRegistry,
)
from c4harness.decompose.compiler import ProposalCompileError, compile_proposal
from c4harness.decompose.proposal import (
    CodexTaskProposal,
    ProposalAcceptanceCriterion,
    ProposalNode,
    ProposalRequirement,
    VerifierPlan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_only_worker(worker_id: str = "reader") -> WorkerArm:
    return WorkerArm(
        id=worker_id,
        backend="test",
        harness="test",
        model="test",
        capabilities=WorkerCapabilities(
            tools=frozenset({"read", "grep", "glob"}),
            context_tokens=100_000,
        ),
    )


def _patch_worker(worker_id: str = "patcher") -> WorkerArm:
    return WorkerArm(
        id=worker_id,
        backend="test",
        harness="test",
        model="test",
        capabilities=WorkerCapabilities(
            tools=frozenset({"read", "grep", "glob", "patch"}),
            write_isolation="staged_copy",
            context_tokens=100_000,
        ),
    )


def _minimal_proposal() -> CodexTaskProposal:
    """Return a valid single-node proposal for mutation in tests."""
    return CodexTaskProposal(
        version=1,
        root_goal="Implement feature X",
        requirements=[
            ProposalRequirement(
                id="R1",
                text="Add the feature",
                kind=RequirementKind.DELIVERABLE,
            ),
        ],
        constraints=["Do not break existing tests"],
        acceptance_criteria=[
            ProposalAcceptanceCriterion(
                id="A1",
                description="Feature works end-to-end",
                check="tests_pass",
                requirement_refs=("R1",),
            ),
        ],
        interaction_mode=InteractionMode.EXECUTE,
        nodes=[
            ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                soft_capability_weights={"code_implementation": 0.8},
                verifier_plan=VerifierPlan(
                    template_checks=["requirement_coverage"],
                    root_contribution="Delivers the feature",
                ),
                root_contribution="Delivers the feature",
            ),
        ],
    )


def _compile(repo: Path, proposal: CodexTaskProposal | None = None, **kw):
    """Shortcut: compile with default single-node proposal and one worker."""
    prop = proposal if proposal is not None else _minimal_proposal()
    registry = kw.pop("registry", WorkerRegistry({"reader": _read_only_worker()}))
    return compile_proposal(prop, repo, registry, **kw)


# ---------------------------------------------------------------------------
# Valid compilation
# ---------------------------------------------------------------------------


class ValidCompilationTests(unittest.TestCase):
    """Happy-path: proposal compiles into a valid DecompositionPlan."""

    def test_single_node_compiles_to_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)

            self.assertEqual(plan.shape, ExecutionShape.FAST_PATH)
            self.assertEqual(len(plan.graph.nodes), 1)
            self.assertIn("n1", plan.graph.nodes)
            self.assertIsNotNone(plan.graph.nodes["n1"].assigned_worker_id)
            plan.validate()

    def test_multi_node_compiles_to_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes.append(
                ProposalNode(
                    node_id="n2",
                    objective="Verify feature X",
                    kind=NodeKind.VERIFY,
                    requirement_refs=("R1",),
                    dependencies=("n1",),
                    hard_capabilities={
                        "modalities": ["text"],
                        "tools": ["read"],
                        "write_isolation": [],
                        "network_required": False,
                        "structured_output_required": False,
                        "min_context_tokens": 0,
                        "persistent_session_required": False,
                        "provider_protocols": [],
                        "privacy_zones": [],
                    },
                    verifier_plan=VerifierPlan(template_checks=["tests_pass"]),
                ),
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            plan = compile_proposal(proposal, repo, registry)

            self.assertEqual(plan.shape, ExecutionShape.GRAPH)
            self.assertEqual(len(plan.graph.nodes), 2)
            self.assertEqual(len(plan.graph.edges), 1)
            self.assertEqual(plan.graph.edges[0].source, "n1")
            self.assertEqual(plan.graph.edges[0].target, "n2")

    def test_plan_mode_forces_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.interaction_mode = InteractionMode.PLAN
            plan = _compile(repo, proposal)

            node = plan.graph.nodes["n1"]
            self.assertEqual(node.execution_mode, ExecutionMode.READ_ONLY)
            self.assertFalse(node.write_paths)
            self.assertTrue(
                any("plan mode" in r for r in plan.reasons)
            )

    def test_risk_manifest_in_assignment_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)

            record = plan.assignment_records["n1"]
            self.assertIn("risk_manifest", record)
            manifest = record["risk_manifest"]
            self.assertIn("destination", manifest)
            self.assertIn("privacy_zone", manifest)
            self.assertIn("transmitted_paths", manifest)
            self.assertIn("write_paths", manifest)
            self.assertIn("execution_mode", manifest)

    def test_hard_capabilities_compiled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)

            hc = plan.graph.nodes["n1"].hard_capabilities
            self.assertIn("text", hc.modalities)
            self.assertIn("read", hc.tools)

    def test_soft_capabilities_compiled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)

            sc = plan.graph.nodes["n1"].soft_capabilities
            self.assertIn("code_implementation", sc)
            self.assertAlmostEqual(sc["code_implementation"], 0.8)

    def test_verifier_plan_compiled_to_verification_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)

            ver = plan.graph.nodes["n1"].verification
            self.assertIn("requirement_coverage", ver.deterministic_checks)
            self.assertEqual(ver.root_contribution, "Delivers the feature")
            self.assertTrue(ver.is_verifiable())

    def test_node_ids_and_dependencies_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes.append(
                ProposalNode(
                    node_id="verify",
                    objective="Verify feature X",
                    kind=NodeKind.VERIFY,
                    requirement_refs=("R1",),
                    dependencies=("n1",),
                    hard_capabilities={
                        "modalities": ["text"],
                        "tools": ["read"],
                        "write_isolation": [],
                        "network_required": False,
                        "structured_output_required": False,
                        "min_context_tokens": 0,
                        "persistent_session_required": False,
                        "provider_protocols": [],
                        "privacy_zones": [],
                    },
                    verifier_plan=VerifierPlan(template_checks=["tests_pass"]),
                ),
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            plan = compile_proposal(proposal, repo, registry)

            self.assertIn("n1", plan.graph.nodes)
            self.assertIn("verify", plan.graph.nodes)
            edge = plan.graph.edges[0]
            self.assertEqual(edge.source, "n1")
            self.assertEqual(edge.target, "verify")

    def test_patch_mode_compiles_with_write_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                write_paths=("src/feature.py",),
                execution_mode=ExecutionMode.PATCH,
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read", "patch"],
                    "write_isolation": ["staged_copy"],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                soft_capability_weights={"code_implementation": 0.8},
                verifier_plan=VerifierPlan(
                    template_checks=["patch_non_empty"],
                    root_contribution="Delivers the feature",
                ),
                root_contribution="Delivers the feature",
            )
            registry = WorkerRegistry({"patcher": _patch_worker()})
            plan = compile_proposal(proposal, repo, registry)

            node = plan.graph.nodes["n1"]
            self.assertEqual(node.execution_mode, ExecutionMode.PATCH)
            self.assertTrue(node.write_paths)

    def test_situation_fields_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            plan = _compile(repo, proposal)

            sit = plan.situation
            self.assertEqual(sit.objective, "Implement feature X")
            self.assertEqual(sit.interaction_mode, InteractionMode.EXECUTE)
            self.assertIn("Do not break existing tests", sit.constraints)
            self.assertEqual(len(sit.requirements.items), 1)
            self.assertEqual(len(sit.root_contract.criteria), 1)
            self.assertIn("reader", sit.available_worker_ids)

    def test_context_packs_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "ctx").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                context_packs=("ctx/info.md",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                soft_capability_weights={"code_implementation": 0.8},
                verifier_plan=VerifierPlan(
                    template_checks=["file_exists:ctx/info.md"],
                    root_contribution="Delivers the feature",
                ),
                root_contribution="Delivers the feature",
            )
            plan = _compile(repo, proposal)

            node = plan.graph.nodes["n1"]
            self.assertEqual(len(node.context_packs), 1)
            self.assertIn("ctx", str(node.context_packs[0]))


# ---------------------------------------------------------------------------
# Invariant violations
# ---------------------------------------------------------------------------


class InvariantViolationTests(unittest.TestCase):
    """Each test exercises exactly one compilation invariant."""

    # -- empty / missing ----------------------------------------------------

    def test_empty_nodes_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal = _minimal_proposal()
            proposal.nodes = []
            with self.assertRaisesRegex(
                ProposalCompileError, "at least one node"
            ):
                _compile(Path(tmp), proposal)

    def test_no_acceptance_criteria_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.acceptance_criteria = []
            with self.assertRaisesRegex(
                ProposalCompileError, "acceptance criterion"
            ):
                _compile(Path(tmp), proposal)

    # -- requirement coverage ------------------------------------------------

    def test_uncovered_required_requirement_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.requirements.append(
                ProposalRequirement(
                    id="R2",
                    text="Another deliverable",
                    kind=RequirementKind.DELIVERABLE,
                ),
            )
            with self.assertRaisesRegex(ProposalCompileError, "R2"):
                _compile(Path(tmp), proposal)

    # -- deliverable root contribution ---------------------------------------

    def test_deliverable_not_in_acceptance_criterion_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = CodexTaskProposal(
                version=1,
                root_goal="Build features A and B",
                requirements=[
                    ProposalRequirement(
                        id="R1",
                        text="Feature A",
                        kind=RequirementKind.DELIVERABLE,
                    ),
                    ProposalRequirement(
                        id="R2",
                        text="Feature B",
                        kind=RequirementKind.DELIVERABLE,
                    ),
                ],
                acceptance_criteria=[
                    ProposalAcceptanceCriterion(
                        id="A1",
                        description="Feature A works",
                        requirement_refs=("R1",),
                    ),
                ],
                nodes=[
                    ProposalNode(
                        node_id="n1",
                        objective="Build features",
                        kind=NodeKind.WORK,
                        requirement_refs=("R1", "R2"),
                        hard_capabilities={
                            "modalities": ["text"],
                            "tools": ["read"],
                            "write_isolation": [],
                            "network_required": False,
                            "structured_output_required": False,
                            "min_context_tokens": 0,
                            "persistent_session_required": False,
                            "provider_protocols": [],
                            "privacy_zones": [],
                        },
                        verifier_plan=VerifierPlan(
                            root_contribution="Delivers features"
                        ),
                    ),
                ],
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(ProposalCompileError, "R2.*root"):
                compile_proposal(proposal, repo, registry)

    # -- constraints as work nodes -------------------------------------------

    def test_constraint_only_work_node_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = CodexTaskProposal(
                version=1,
                root_goal="Respect constraint C1",
                requirements=[
                    ProposalRequirement(
                        id="C1",
                        text="No side effects",
                        kind=RequirementKind.CONSTRAINT,
                    ),
                ],
                acceptance_criteria=[
                    ProposalAcceptanceCriterion(
                        id="A1",
                        description="Constraint respected",
                        requirement_refs=("C1",),
                    ),
                ],
                nodes=[
                    ProposalNode(
                        node_id="n1",
                        objective="Respect constraint C1",
                        kind=NodeKind.WORK,
                        requirement_refs=("C1",),
                        hard_capabilities={
                            "modalities": ["text"],
                            "tools": ["read"],
                            "write_isolation": [],
                            "network_required": False,
                            "structured_output_required": False,
                            "min_context_tokens": 0,
                            "persistent_session_required": False,
                            "provider_protocols": [],
                            "privacy_zones": [],
                        },
                        verifier_plan=VerifierPlan(
                            root_contribution="Ensures C1"
                        ),
                    ),
                ],
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "constraints must not become work nodes"
            ):
                compile_proposal(proposal, repo, registry)

    # -- plan mode -----------------------------------------------------------

    def test_plan_mode_with_patch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.interaction_mode = InteractionMode.PLAN
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                write_paths=("src/module.py",),
                execution_mode=ExecutionMode.PATCH,
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read", "patch"],
                    "write_isolation": ["staged_copy"],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"patcher": _patch_worker()})
            with self.assertRaisesRegex(ProposalCompileError, "plan mode"):
                compile_proposal(proposal, repo, registry)

    # -- path safety ---------------------------------------------------------

    def test_allowed_path_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("/etc/passwd",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "outside repository"
            ):
                compile_proposal(proposal, repo, registry)

    def test_write_path_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                write_paths=("/tmp/evil.py",),
                execution_mode=ExecutionMode.PATCH,
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read", "patch"],
                    "write_isolation": ["staged_copy"],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"patcher": _patch_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "outside repository"
            ):
                compile_proposal(proposal, repo, registry)

    def test_context_pack_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                context_packs=("/etc/shadow",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "outside repository"
            ):
                compile_proposal(proposal, repo, registry)

    def test_path_traversal_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("../../escape",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "outside repository"
            ):
                compile_proposal(proposal, repo, registry)

    # -- execution mode / write scope consistency ----------------------------

    def test_patch_without_write_paths_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                execution_mode=ExecutionMode.PATCH,
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read", "patch"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"patcher": _patch_worker()})
            with self.assertRaisesRegex(ProposalCompileError, "no write_paths"):
                compile_proposal(proposal, repo, registry)

    def test_write_paths_with_read_only_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                write_paths=("src/module.py",),
                execution_mode=ExecutionMode.READ_ONLY,
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                verifier_plan=VerifierPlan(root_contribution="Delivers"),
                root_contribution="Delivers",
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "write_paths.*read_only"
            ):
                compile_proposal(proposal, repo, registry)

    # -- graph structure -----------------------------------------------------

    def test_cyclic_dependency_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = CodexTaskProposal(
                version=1,
                root_goal="test",
                requirements=[
                    ProposalRequirement(
                        id="R1",
                        text="test",
                        kind=RequirementKind.DELIVERABLE,
                    ),
                ],
                acceptance_criteria=[
                    ProposalAcceptanceCriterion(
                        id="A1",
                        description="works",
                        requirement_refs=("R1",),
                    ),
                ],
                nodes=[
                    ProposalNode(
                        node_id="n1",
                        objective="first",
                        kind=NodeKind.WORK,
                        requirement_refs=("R1",),
                        dependencies=("n2",),
                        hard_capabilities={
                            "modalities": ["text"],
                            "tools": ["read"],
                            "write_isolation": [],
                            "network_required": False,
                            "structured_output_required": False,
                            "min_context_tokens": 0,
                            "persistent_session_required": False,
                            "provider_protocols": [],
                            "privacy_zones": [],
                        },
                        verifier_plan=VerifierPlan(
                            root_contribution="contributes"
                        ),
                    ),
                    ProposalNode(
                        node_id="n2",
                        objective="second",
                        kind=NodeKind.WORK,
                        requirement_refs=("R1",),
                        dependencies=("n1",),
                        hard_capabilities={
                            "modalities": ["text"],
                            "tools": ["read"],
                            "write_isolation": [],
                            "network_required": False,
                            "structured_output_required": False,
                            "min_context_tokens": 0,
                            "persistent_session_required": False,
                            "provider_protocols": [],
                            "privacy_zones": [],
                        },
                        verifier_plan=VerifierPlan(
                            root_contribution="contributes"
                        ),
                    ),
                ],
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(ProposalCompileError, "acyclic"):
                compile_proposal(proposal, repo, registry)

    def test_dangling_dependency_raises(self) -> None:
        """A dependency on a non-existent node is caught by the compiler."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proposal = CodexTaskProposal(
                version=1,
                root_goal="test",
                requirements=[
                    ProposalRequirement(
                        id="R1",
                        text="test",
                        kind=RequirementKind.DELIVERABLE,
                    ),
                ],
                acceptance_criteria=[
                    ProposalAcceptanceCriterion(
                        id="A1",
                        description="works",
                        requirement_refs=("R1",),
                    ),
                ],
                nodes=[
                    ProposalNode(
                        node_id="n1",
                        objective="first",
                        kind=NodeKind.WORK,
                        requirement_refs=("R1",),
                        dependencies=("ghost",),
                        hard_capabilities={
                            "modalities": ["text"],
                            "tools": ["read"],
                            "write_isolation": [],
                            "network_required": False,
                            "structured_output_required": False,
                            "min_context_tokens": 0,
                            "persistent_session_required": False,
                            "provider_protocols": [],
                            "privacy_zones": [],
                        },
                        verifier_plan=VerifierPlan(
                            root_contribution="contributes"
                        ),
                    ),
                ],
            )
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(ProposalCompileError, "ghost"):
                compile_proposal(proposal, repo, registry)

    # -- worker assignment ---------------------------------------------------

    def test_no_eligible_worker_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            registry = WorkerRegistry()
            with self.assertRaisesRegex(
                ProposalCompileError, "No eligible worker"
            ):
                compile_proposal(proposal, repo, registry)

    def test_hard_capability_mismatch_raises(self) -> None:
        """A worker missing required tools triggers assignment failure."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            proposal = _minimal_proposal()
            proposal.nodes[0] = ProposalNode(
                node_id="n1",
                objective="Implement feature X",
                kind=NodeKind.WORK,
                requirement_refs=("R1",),
                allowed_paths=("src/",),
                hard_capabilities={
                    "modalities": ["text"],
                    "tools": ["read", "patch"],
                    "write_isolation": [],
                    "network_required": False,
                    "structured_output_required": False,
                    "min_context_tokens": 0,
                    "persistent_session_required": False,
                    "provider_protocols": [],
                    "privacy_zones": [],
                },
                soft_capability_weights={"code_implementation": 0.8},
                verifier_plan=VerifierPlan(
                    template_checks=["requirement_coverage"],
                    root_contribution="Delivers",
                ),
                root_contribution="Delivers",
            )
            # Only a read-only worker; node requires "patch" tool.
            registry = WorkerRegistry({"reader": _read_only_worker()})
            with self.assertRaisesRegex(
                ProposalCompileError, "No eligible worker"
            ):
                compile_proposal(proposal, repo, registry)

    # -- verify plan.validate() runs ----------------------------------------

    def test_plan_validate_runs_after_compilation(self) -> None:
        """The returned plan must be structurally valid."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)
            # plan.validate() is called inside compile_proposal;
            # calling again should not raise.
            plan.validate()

    def test_all_required_requirements_covered_by_graph(self) -> None:
        """Graph requirement_coverage includes all required ids."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            plan = _compile(repo)
            required = plan.situation.requirements.required_ids()
            covered = plan.graph.requirement_coverage()
            self.assertTrue(required.issubset(covered))


if __name__ == "__main__":
    unittest.main()
