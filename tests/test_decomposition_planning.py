from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.core.contracts import Task
from cost_router.decompose import (
    Requirement,
    RequirementKind,
    TaskSituationBuilder,
)
from cost_router.decompose.atomicity import assess_shape
from cost_router.decompose.operators import (
    deliverable_split,
    evidence_split,
    workflow_split,
)


class PlanningOperatorTests(unittest.TestCase):
    def situation(self, **kwargs):
        root = Path(tempfile.mkdtemp())
        return TaskSituationBuilder().from_task(Task(goal="Build feature", repo=root), **kwargs)

    def test_deliverables_trigger_parallel_graph(self) -> None:
        situation = self.situation(
            requirements=[
                Requirement("R1", "Implement API", RequirementKind.DELIVERABLE),
                Requirement("R2", "Write docs", RequirementKind.DELIVERABLE),
                Requirement("C1", "No network", RequirementKind.CONSTRAINT),
            ]
        )
        proposal = deliverable_split(situation)
        self.assertIsNotNone(proposal)
        self.assertFalse(proposal and proposal.sequential)
        self.assertEqual(assess_shape(situation).shape.value, "graph")

    def test_skill_steps_trigger_sequential_graph(self) -> None:
        situation = self.situation(skill_steps=["Inspect", "Implement", "Verify"])
        proposal = workflow_split(situation)
        self.assertTrue(proposal and proposal.sequential)

    def test_unresolved_questions_create_evidence_signal(self) -> None:
        situation = self.situation(unresolved_questions=["Which API is public?"])
        self.assertIsNotNone(evidence_split(situation))

    def test_simple_goal_stays_fast_path(self) -> None:
        self.assertEqual(assess_shape(self.situation()).shape.value, "fast_path")


if __name__ == "__main__":
    unittest.main()
