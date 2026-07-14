from __future__ import annotations

import unittest

from c4harness.decompose import (
    HardCapabilityRequirements,
    TaskNodeContract,
    VerificationContract,
    WorkerArm,
    WorkerCapabilities,
    WorkerAssignmentPolicy,
    WorkerRegistry,
)
from c4harness.history import CapabilityEvidence, CapabilityProfile


def worker(worker_id: str, *, tools=("read",), soft=0.5) -> WorkerArm:
    return WorkerArm(
        id=worker_id,
        backend="test",
        harness="test",
        model="test",
        capabilities=WorkerCapabilities(tools=frozenset(tools), soft={"debugging": soft}),
    )


class AssignmentTests(unittest.TestCase):
    def node(self) -> TaskNodeContract:
        return TaskNodeContract(
            objective="debug",
            hard_capabilities=HardCapabilityRequirements(tools=frozenset({"read"})),
            soft_capabilities={"debugging": 1.0},
            verification=VerificationContract(evidence_requirements=("evidence",)),
        )

    def test_exact_hard_failure_reasons_are_preserved(self) -> None:
        registry = WorkerRegistry({"bad": worker("bad", tools=())})
        with self.assertRaisesRegex(ValueError, "missing tools: read"):
            WorkerAssignmentPolicy().assign(self.node(), registry)

    def test_preference_and_history_are_explainable(self) -> None:
        registry = WorkerRegistry({"a": worker("a"), "b": worker("b")})
        profile = CapabilityProfile(
            "b",
            (CapabilityEvidence("b", "debugging", verified_successes=4, verified_failures=1),),
        )
        decision = WorkerAssignmentPolicy().assign(
            self.node(), registry,
            worker_preferences={"b": 0.5},
            capability_profiles={"b": profile},
        )
        self.assertEqual(decision.worker_id, "b")
        selected = next(item for item in decision.candidates if item.worker_id == "b")
        self.assertIsNotNone(selected.breakdown)
        self.assertGreater(decision.confidence, 0.0)
        self.assertIn("confidence_factors", decision.to_dict())


if __name__ == "__main__":
    unittest.main()
