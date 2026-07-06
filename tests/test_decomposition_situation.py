from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cost_router.core.contracts import (
    DataClassification,
    ExternalPolicy,
    Task,
    TaskConstraints,
)
from cost_router.decompose import (
    AcceptanceCriterion,
    InteractionMode,
    Requirement,
    RequirementKind,
    TaskSituationBuilder,
)


class TaskSituationTests(unittest.TestCase):
    def test_defaults_are_deterministic_and_cover_the_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="Inspect the parser", repo=Path(tmp), id="task_fixed")
            first = TaskSituationBuilder().from_task(task)
            second = TaskSituationBuilder().from_task(task)
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(first.requirements.required_ids(), {"R1"})
            self.assertEqual(
                first.root_contract.criteria[0].requirement_refs,
                ("R1",),
            )

    def test_explicit_requirements_acceptance_skill_and_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(goal="Plan a migration", repo=Path(tmp))
            situation = TaskSituationBuilder().from_task(
                task,
                requirements=[
                    Requirement("R1", "Design migration", RequirementKind.DELIVERABLE),
                    Requirement("C1", "Do not edit", RequirementKind.CONSTRAINT),
                ],
                acceptance_criteria=[
                    AcceptanceCriterion(
                        "A1",
                        "Both requirements are addressed",
                        requirement_refs=("R1", "C1"),
                    )
                ],
                interaction_mode=InteractionMode.PLAN,
                active_skills=["migration"],
                skill_steps=["Inspect", "Plan"],
                environment_facts=["language=python"],
                unresolved_questions=["Which API is public?"],
                historical_profile_summary=["claude:debugging=0.8"],
                security_context=["private"],
            )
            self.assertEqual(situation.interaction_mode, InteractionMode.PLAN)
            self.assertEqual(situation.requirements.required_ids(), {"R1", "C1"})
            self.assertEqual(situation.skill_steps, ("Inspect", "Plan"))
            self.assertEqual(situation.historical_profile_summary, ("claude:debugging=0.8",))

    def test_security_policy_is_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(
                goal="Review private code",
                repo=Path(tmp),
                constraints=TaskConstraints(
                    external_policy=ExternalPolicy.ALLOW,
                    data_classification=DataClassification.PRIVATE,
                ),
            )
            situation = TaskSituationBuilder().from_task(task)
            self.assertIn("external_policy=allow", situation.constraints)
            self.assertIn("data_classification=private", situation.constraints)


if __name__ == "__main__":
    unittest.main()
