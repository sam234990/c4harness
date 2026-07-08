"""Tests for Codex task proposal parsing and validation."""

from __future__ import annotations

import json
import unittest

from cost_router.decompose.proposal import (
    CodexTaskProposal,
    ProposalAcceptanceCriterion,
    ProposalNode,
    ProposalParseError,
    ProposalRequirement,
    VerifierPlan,
)
from cost_router.decompose.models import (
    ExecutionMode,
    InteractionMode,
    NodeKind,
    RequirementKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_proposal_dict() -> dict:
    """Return a valid minimal proposal dict for mutation in tests."""
    return {
        "version": 1,
        "root_goal": "Implement feature X",
        "requirements": [
            {"id": "R1", "text": "Add the feature", "kind": "deliverable", "required": True}
        ],
        "constraints": ["Do not break existing tests"],
        "acceptance_criteria": [
            {
                "id": "A1",
                "description": "Feature works end-to-end",
                "check": "tests_pass",
                "requirement_refs": ["R1"],
            }
        ],
        "interaction_mode": "execute",
        "unresolved_questions": [],
        "nodes": [
            {
                "node_id": "n1",
                "objective": "Implement feature X",
                "kind": "work",
                "requirement_refs": ["R1"],
                "dependencies": [],
                "context_packs": [],
                "allowed_paths": ["src/"],
                "artifact_inputs": [],
                "write_paths": [],
                "execution_mode": "read_only",
                "output_type": "report",
                "hard_capabilities": {
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
                "soft_capability_weights": {
                    "code_implementation": 0.8,
                },
                "verifier_plan": {
                    "template_checks": ["patch_non_empty"],
                    "evidence_requirements": [],
                    "semantic_criteria": [],
                    "root_contribution": "Delivers the feature",
                    "inconclusive_policy": "fail",
                },
                "root_contribution": "Delivers the feature",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Valid round-trip
# ---------------------------------------------------------------------------


class RoundTripTests(unittest.TestCase):
    """Verify that from_dict -> to_dict -> from_dict is lossless."""

    def test_minimal_proposal_round_trips(self) -> None:
        data = _minimal_proposal_dict()
        proposal = CodexTaskProposal.from_dict(data)
        serialised = proposal.to_dict()
        self.assertEqual(serialised, data)
        # Re-parse from serialised
        proposal2 = CodexTaskProposal.from_dict(serialised)
        self.assertEqual(proposal2.to_dict(), data)

    def test_json_round_trip(self) -> None:
        data = _minimal_proposal_dict()
        proposal = CodexTaskProposal.from_dict(data)
        json_str = proposal.to_json()
        proposal2 = CodexTaskProposal.from_json(json_str)
        self.assertEqual(proposal2.to_dict(), data)

    def test_multi_node_proposal_round_trips(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"].append(
            {
                "node_id": "n2",
                "objective": "Verify the feature",
                "kind": "verify",
                "requirement_refs": ["R1"],
                "dependencies": ["n1"],
                "context_packs": [],
                "allowed_paths": [],
                "artifact_inputs": [],
                "write_paths": [],
                "execution_mode": "read_only",
                "output_type": "report",
                "hard_capabilities": {
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
                "soft_capability_weights": {},
                "verifier_plan": {
                    "template_checks": ["tests_pass"],
                    "evidence_requirements": [],
                    "semantic_criteria": [],
                    "root_contribution": "Verifies the feature",
                    "inconclusive_policy": "fail",
                },
                "root_contribution": "Verifies the feature",
            }
        )
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(len(proposal.nodes), 2)
        self.assertEqual(proposal.to_dict(), data)

    def test_plan_mode_round_trips(self) -> None:
        data = _minimal_proposal_dict()
        data["interaction_mode"] = "plan"
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(proposal.interaction_mode, InteractionMode.PLAN)
        self.assertEqual(proposal.to_dict()["interaction_mode"], "plan")

    def test_all_node_kinds_round_trip(self) -> None:
        """Every NodeKind value can be used in a proposal."""
        for kind in NodeKind:
            data = _minimal_proposal_dict()
            data["nodes"][0]["kind"] = kind.value
            proposal = CodexTaskProposal.from_dict(data)
            self.assertEqual(proposal.nodes[0].kind, kind)

    def test_all_requirement_kinds_round_trip(self) -> None:
        for kind in RequirementKind:
            data = _minimal_proposal_dict()
            data["requirements"][0]["kind"] = kind.value
            proposal = CodexTaskProposal.from_dict(data)
            self.assertEqual(proposal.requirements[0].kind, kind)

    def test_all_execution_modes_round_trip(self) -> None:
        """Every ExecutionMode value can be used in a proposal node."""
        for mode in ExecutionMode:
            data = _minimal_proposal_dict()
            data["nodes"][0]["execution_mode"] = mode.value
            proposal = CodexTaskProposal.from_dict(data)
            self.assertEqual(proposal.nodes[0].execution_mode, mode)
            self.assertEqual(proposal.to_dict()["nodes"][0]["execution_mode"], mode.value)

    def test_component_from_dict_round_trips(self) -> None:
        """Individual component dataclasses also round-trip."""
        req = ProposalRequirement.from_dict(
            {"id": "R1", "text": "test", "kind": "deliverable", "required": True}
        )
        self.assertEqual(req.to_dict()["id"], "R1")

        ac = ProposalAcceptanceCriterion.from_dict(
            {"id": "A1", "description": "works", "check": "tests_pass", "requirement_refs": ["R1"]}
        )
        self.assertEqual(ac.to_dict()["id"], "A1")

        vp = VerifierPlan.from_dict(
            {
                "template_checks": ["file_exists"],
                "evidence_requirements": [],
                "semantic_criteria": [],
                "root_contribution": "contributes",
                "inconclusive_policy": "fail",
            }
        )
        self.assertEqual(vp.to_dict()["template_checks"], ["file_exists"])

    def test_proposal_node_new_fields_round_trip(self) -> None:
        """artifact_inputs, write_paths, execution_mode, output_type round-trip."""
        data = _minimal_proposal_dict()
        data["nodes"][0]["artifact_inputs"] = ["build/output.json", "logs/run.txt"]
        data["nodes"][0]["write_paths"] = ["src/module.py", "tests/test_module.py"]
        data["nodes"][0]["execution_mode"] = "patch"
        data["nodes"][0]["output_type"] = "patch"
        proposal = CodexTaskProposal.from_dict(data)
        node = proposal.nodes[0]
        self.assertEqual(node.artifact_inputs, ("build/output.json", "logs/run.txt"))
        self.assertEqual(node.write_paths, ("src/module.py", "tests/test_module.py"))
        self.assertEqual(node.execution_mode, ExecutionMode.PATCH)
        self.assertEqual(node.output_type, "patch")
        serialised = proposal.to_dict()
        self.assertEqual(serialised, data)
        # Double round-trip
        proposal2 = CodexTaskProposal.from_dict(serialised)
        self.assertEqual(proposal2.to_dict(), data)

    def test_node_default_new_fields(self) -> None:
        """New node fields default correctly when omitted."""
        data = _minimal_proposal_dict()
        # Remove new fields from the dict to test defaults
        for key in ("artifact_inputs", "write_paths", "execution_mode", "output_type"):
            del data["nodes"][0][key]
        proposal = CodexTaskProposal.from_dict(data)
        node = proposal.nodes[0]
        self.assertEqual(node.artifact_inputs, ())
        self.assertEqual(node.write_paths, ())
        self.assertEqual(node.execution_mode, ExecutionMode.READ_ONLY)
        self.assertEqual(node.output_type, "report")


# ---------------------------------------------------------------------------
# Invalid: unknown fields
# ---------------------------------------------------------------------------


class UnknownFieldTests(unittest.TestCase):
    """Strict rejection of unknown fields at every level."""

    def test_unknown_top_level_field(self) -> None:
        data = _minimal_proposal_dict()
        data["unknown_field"] = "oops"
        with self.assertRaisesRegex(ProposalParseError, r"\$.*unknown field.*unknown_field"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_requirement_field(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"][0]["extra"] = True
        with self.assertRaisesRegex(ProposalParseError, r"requirements\[0\].*unknown field.*extra"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_node_field(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["mystery"] = 42
        with self.assertRaisesRegex(ProposalParseError, r"nodes\[0\].*unknown field.*mystery"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_hard_capability_field(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["hard_capabilities"]["telepathy"] = True
        with self.assertRaisesRegex(ProposalParseError, r"hard_capabilities.*unknown field.*telepathy"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_verifier_plan_field(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["verifier_plan"]["extra_check"] = True
        with self.assertRaisesRegex(ProposalParseError, r"verifier_plan.*unknown field.*extra_check"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_acceptance_criterion_field(self) -> None:
        data = _minimal_proposal_dict()
        data["acceptance_criteria"][0]["bonus"] = True
        with self.assertRaisesRegex(ProposalParseError, r"acceptance_criteria\[0\].*unknown field.*bonus"):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Invalid: duplicate IDs
# ---------------------------------------------------------------------------


class DuplicateIdTests(unittest.TestCase):
    def test_duplicate_requirement_id(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"].append(
            {"id": "R1", "text": "duplicate", "kind": "deliverable", "required": True}
        )
        with self.assertRaisesRegex(ProposalParseError, r"duplicate requirement id.*R1"):
            CodexTaskProposal.from_dict(data)

    def test_duplicate_node_id(self) -> None:
        data = _minimal_proposal_dict()
        dup = dict(data["nodes"][0])
        data["nodes"].append(dup)
        with self.assertRaisesRegex(ProposalParseError, r"duplicate node id.*n1"):
            CodexTaskProposal.from_dict(data)

    def test_duplicate_acceptance_criterion_id(self) -> None:
        data = _minimal_proposal_dict()
        data["acceptance_criteria"].append(dict(data["acceptance_criteria"][0]))
        with self.assertRaisesRegex(ProposalParseError, r"duplicate acceptance criterion id.*A1"):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Invalid: dangling references
# ---------------------------------------------------------------------------


class DanglingReferenceTests(unittest.TestCase):
    def test_node_references_unknown_requirement(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["requirement_refs"] = ["R1", "R_NONEXISTENT"]
        with self.assertRaisesRegex(
            ProposalParseError, r"n1.*unknown requirement.*R_NONEXISTENT"
        ):
            CodexTaskProposal.from_dict(data)

    def test_node_depends_on_unknown_node(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["dependencies"] = ["ghost_node"]
        with self.assertRaisesRegex(
            ProposalParseError, r"n1.*unknown node.*ghost_node"
        ):
            CodexTaskProposal.from_dict(data)

    def test_node_self_dependency(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["dependencies"] = ["n1"]
        with self.assertRaisesRegex(ProposalParseError, r"n1.*cannot depend on itself"):
            CodexTaskProposal.from_dict(data)

    def test_acceptance_criterion_references_unknown_requirement(self) -> None:
        data = _minimal_proposal_dict()
        data["acceptance_criteria"][0]["requirement_refs"] = ["R1", "R_GHOST"]
        with self.assertRaisesRegex(
            ProposalParseError, r"A1.*unknown requirement.*R_GHOST"
        ):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Invalid: enum values
# ---------------------------------------------------------------------------


class InvalidEnumTests(unittest.TestCase):
    def test_invalid_interaction_mode(self) -> None:
        data = _minimal_proposal_dict()
        data["interaction_mode"] = "turbo"
        with self.assertRaisesRegex(ProposalParseError, r"interaction_mode.*turbo"):
            CodexTaskProposal.from_dict(data)

    def test_invalid_node_kind(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["kind"] = "magic"
        with self.assertRaisesRegex(ProposalParseError, r"kind.*magic"):
            CodexTaskProposal.from_dict(data)

    def test_invalid_requirement_kind(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"][0]["kind"] = "wishful"
        with self.assertRaisesRegex(ProposalParseError, r"kind.*wishful"):
            CodexTaskProposal.from_dict(data)

    def test_invalid_execution_mode(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["execution_mode"] = "turbo"
        with self.assertRaisesRegex(ProposalParseError, r"execution_mode.*turbo"):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Invalid: malformed capability weights
# ---------------------------------------------------------------------------


class CapabilityWeightTests(unittest.TestCase):
    def test_weight_out_of_range_high(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["code_implementation"] = 1.5
        with self.assertRaisesRegex(ProposalParseError, r"in \[0, 1\]"):
            CodexTaskProposal.from_dict(data)

    def test_weight_out_of_range_negative(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["debugging"] = -0.1
        with self.assertRaisesRegex(ProposalParseError, r"in \[0, 1\]"):
            CodexTaskProposal.from_dict(data)

    def test_weight_not_a_number(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["debugging"] = "high"
        with self.assertRaisesRegex(ProposalParseError, r"must be a number"):
            CodexTaskProposal.from_dict(data)

    def test_weight_bool_rejected(self) -> None:
        """bool is a subclass of int; must be explicitly rejected."""
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["debugging"] = True
        with self.assertRaisesRegex(ProposalParseError, r"must be a number.*bool"):
            CodexTaskProposal.from_dict(data)

    def test_weight_bool_false_rejected(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["debugging"] = False
        with self.assertRaisesRegex(ProposalParseError, r"must be a number.*bool"):
            CodexTaskProposal.from_dict(data)

    def test_unknown_soft_capability_dimension(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"]["telepathy"] = 0.9
        with self.assertRaisesRegex(ProposalParseError, r"unknown soft capability dimension.*telepathy"):
            CodexTaskProposal.from_dict(data)

    def test_weights_not_a_dict(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["soft_capability_weights"] = [0.5]
        with self.assertRaisesRegex(ProposalParseError, r"must be a dict"):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Invalid: structural / type errors
# ---------------------------------------------------------------------------


class StructuralErrorTests(unittest.TestCase):
    def test_proposal_not_a_dict(self) -> None:
        with self.assertRaisesRegex(ProposalParseError, r"proposal must be a dict"):
            CodexTaskProposal.from_dict("not a dict")  # type: ignore[arg-type]

    def test_requirements_not_a_list(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"] = "R1"
        with self.assertRaisesRegex(ProposalParseError, r"'requirements' must be a list"):
            CodexTaskProposal.from_dict(data)

    def test_nodes_not_a_list(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"] = {"node_id": "n1"}
        with self.assertRaisesRegex(ProposalParseError, r"'nodes' must be a list"):
            CodexTaskProposal.from_dict(data)

    def test_requirement_not_a_dict(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"] = ["R1"]
        with self.assertRaisesRegex(ProposalParseError, r"item must be a dict"):
            CodexTaskProposal.from_dict(data)

    def test_node_not_a_dict(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"] = ["n1"]
        with self.assertRaisesRegex(ProposalParseError, r"item must be a dict"):
            CodexTaskProposal.from_dict(data)

    def test_missing_root_goal(self) -> None:
        data = _minimal_proposal_dict()
        del data["root_goal"]
        with self.assertRaisesRegex(ProposalParseError, r"missing required field.*root_goal"):
            CodexTaskProposal.from_dict(data)

    def test_missing_version(self) -> None:
        data = _minimal_proposal_dict()
        del data["version"]
        with self.assertRaisesRegex(ProposalParseError, r"missing required field.*version"):
            CodexTaskProposal.from_dict(data)

    def test_version_not_int(self) -> None:
        data = _minimal_proposal_dict()
        data["version"] = "1"
        with self.assertRaisesRegex(ProposalParseError, r"must be an integer"):
            CodexTaskProposal.from_dict(data)

    def test_version_bool_rejected(self) -> None:
        data = _minimal_proposal_dict()
        data["version"] = True
        with self.assertRaisesRegex(ProposalParseError, r"must be an integer"):
            CodexTaskProposal.from_dict(data)

    def test_version_must_be_one(self) -> None:
        data = _minimal_proposal_dict()
        data["version"] = 2
        with self.assertRaisesRegex(ProposalParseError, r"unsupported schema version.*2"):
            CodexTaskProposal.from_dict(data)

    def test_version_zero_rejected(self) -> None:
        data = _minimal_proposal_dict()
        data["version"] = 0
        with self.assertRaisesRegex(ProposalParseError, r"unsupported schema version.*0"):
            CodexTaskProposal.from_dict(data)

    def test_node_objective_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["objective"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'objective' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_node_id_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["node_id"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'node_id' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_root_goal_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["root_goal"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'root_goal' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_requirement_id_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"][0]["id"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'id' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_requirement_text_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"][0]["text"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'text' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_acceptance_criterion_id_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["acceptance_criteria"][0]["id"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'id' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_acceptance_criterion_description_empty(self) -> None:
        data = _minimal_proposal_dict()
        data["acceptance_criteria"][0]["description"] = ""
        with self.assertRaisesRegex(ProposalParseError, r"field 'description' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_whitespace_only_string_rejected(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["objective"] = "   "
        with self.assertRaisesRegex(ProposalParseError, r"field 'objective' must not be empty"):
            CodexTaskProposal.from_dict(data)

    def test_verifier_plan_not_a_dict(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["verifier_plan"] = "checks"
        with self.assertRaisesRegex(ProposalParseError, r"'verifier_plan' must be a dict"):
            CodexTaskProposal.from_dict(data)

    def test_hard_capabilities_not_a_dict(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["hard_capabilities"] = ["read"]
        with self.assertRaisesRegex(ProposalParseError, r"'hard_capabilities' must be a dict"):
            CodexTaskProposal.from_dict(data)

    def test_invalid_json_string(self) -> None:
        with self.assertRaisesRegex(ProposalParseError, r"invalid JSON"):
            CodexTaskProposal.from_json("{not valid json")

    def test_min_context_tokens_not_int(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["hard_capabilities"]["min_context_tokens"] = "big"
        with self.assertRaisesRegex(ProposalParseError, r"must be an integer"):
            CodexTaskProposal.from_dict(data)

    def test_execution_mode_not_a_string(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["execution_mode"] = 42
        with self.assertRaisesRegex(ProposalParseError, r"'execution_mode' must be a string"):
            CodexTaskProposal.from_dict(data)

    def test_output_type_not_a_string(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["output_type"] = 42
        with self.assertRaisesRegex(ProposalParseError, r"'output_type' must be a string"):
            CodexTaskProposal.from_dict(data)

    def test_artifact_inputs_not_a_list(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["artifact_inputs"] = "file.txt"
        with self.assertRaisesRegex(ProposalParseError, r"'artifact_inputs' must be a list"):
            CodexTaskProposal.from_dict(data)

    def test_write_paths_not_a_list(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["write_paths"] = "src/"
        with self.assertRaisesRegex(ProposalParseError, r"'write_paths' must be a list"):
            CodexTaskProposal.from_dict(data)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class EdgeCaseTests(unittest.TestCase):
    def test_empty_nodes_list_is_valid(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"] = []
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(len(proposal.nodes), 0)

    def test_empty_requirements_list_is_valid(self) -> None:
        data = _minimal_proposal_dict()
        data["requirements"] = []
        data["nodes"][0]["requirement_refs"] = []
        data["acceptance_criteria"][0]["requirement_refs"] = []
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(len(proposal.requirements), 0)

    def test_optional_fields_default_gracefully(self) -> None:
        """Minimal dict with only required fields parses correctly."""
        data = {
            "version": 1,
            "root_goal": "test",
            "requirements": [],
            "nodes": [],
        }
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(proposal.interaction_mode, InteractionMode.EXECUTE)
        self.assertEqual(proposal.constraints, [])
        self.assertEqual(proposal.unresolved_questions, [])

    def test_json_output_is_valid_json(self) -> None:
        data = _minimal_proposal_dict()
        proposal = CodexTaskProposal.from_dict(data)
        parsed = json.loads(proposal.to_json())
        self.assertEqual(parsed["root_goal"], "Implement feature X")

    def test_context_path_scopes_preserved(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["context_packs"] = ["context_pack/001.md"]
        data["nodes"][0]["allowed_paths"] = ["src/", "tests/"]
        proposal = CodexTaskProposal.from_dict(data)
        self.assertEqual(proposal.nodes[0].context_packs, ("context_pack/001.md",))
        self.assertEqual(proposal.nodes[0].allowed_paths, ("src/", "tests/"))

    def test_verifier_plan_fields_preserved(self) -> None:
        data = _minimal_proposal_dict()
        data["nodes"][0]["verifier_plan"] = {
            "template_checks": ["file_exists", "tests_pass"],
            "evidence_requirements": ["test_output.txt"],
            "semantic_criteria": ["Code is idiomatic"],
            "root_contribution": "Delivers the main feature",
            "inconclusive_policy": "retry",
        }
        proposal = CodexTaskProposal.from_dict(data)
        vp = proposal.nodes[0].verifier_plan
        self.assertEqual(vp.template_checks, ("file_exists", "tests_pass"))
        self.assertEqual(vp.evidence_requirements, ("test_output.txt",))
        self.assertEqual(vp.semantic_criteria, ("Code is idiomatic",))
        self.assertEqual(vp.inconclusive_policy, "retry")

    def test_known_fields_are_class_variables(self) -> None:
        """_KNOWN_FIELDS must be ClassVar, not instance field descriptors."""
        for cls in (
            ProposalRequirement,
            ProposalAcceptanceCriterion,
            VerifierPlan,
            ProposalNode,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertIsInstance(cls._KNOWN_FIELDS, set)
                self.assertGreater(len(cls._KNOWN_FIELDS), 0)


if __name__ == "__main__":
    unittest.main()
