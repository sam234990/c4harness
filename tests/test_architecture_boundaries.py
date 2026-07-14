from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from c4harness.application import PrepareTask
from c4harness.core.contracts import Task
from c4harness.decompose import (
    BoundedReplanner,
    DecompositionService,
    ReplanAction,
    ReplanReason,
    ReplanRequest,
    WorkerArm,
    WorkerCapabilities,
    WorkerRegistry,
)
from c4harness.history import (
    ExecutionOutcome,
    FailureAttribution,
    InMemoryHistoryRepository,
    OutcomeStatus,
    build_capability_profile,
)
from c4harness.memory import MemoryStore


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_application_records_plan_in_history_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = WorkerArm(
                id="reader",
                backend="test",
                harness="test",
                model="test",
                capabilities=WorkerCapabilities(tools=frozenset({"read"})),
            )
            service = DecompositionService(
                store=MemoryStore(root / "legacy-memory.sqlite3"),
                registry=WorkerRegistry({worker.id: worker}),
            )
            history = InMemoryHistoryRepository()

            plan = PrepareTask(service, history).execute(
                Task(goal="inspect one bounded input", repo=root)
            )

            self.assertEqual(len(history.plans), 1)
            self.assertEqual(history.plans[0].task_id, plan.situation.task_id)
            self.assertEqual(history.plans[0].payload["shape"], "fast_path")

    def test_policy_and_environment_failures_do_not_penalize_worker_profile(self) -> None:
        outcomes = [
            ExecutionOutcome(
                task_id="t1",
                node_id="n1",
                worker_arm_id="claude",
                status=OutcomeStatus.SUCCESS,
                capability_dimensions=("debugging",),
                total_tokens=100,
            ),
            ExecutionOutcome(
                task_id="t2",
                node_id="n2",
                worker_arm_id="claude",
                status=OutcomeStatus.FAILED,
                capability_dimensions=("debugging",),
                failure_attribution=FailureAttribution.PERMISSION_BLOCKED,
                total_tokens=0,
            ),
            ExecutionOutcome(
                task_id="t3",
                node_id="n3",
                worker_arm_id="claude",
                status=OutcomeStatus.FAILED,
                capability_dimensions=("debugging",),
                failure_attribution=FailureAttribution.WORKER_ERROR,
                total_tokens=50,
            ),
        ]

        profile = build_capability_profile("claude", outcomes)
        evidence = profile.evidence[0]
        self.assertEqual(evidence.verified_successes, 1)
        self.assertEqual(evidence.verified_failures, 1)
        self.assertEqual(evidence.excluded_count, 1)
        self.assertEqual(evidence.usable_sample_count, 2)

    def test_replanner_keeps_policy_blocks_out_of_worker_retry_loop(self) -> None:
        decision = BoundedReplanner().decide(
            ReplanRequest(
                task_id="t1",
                node_id="n1",
                reason=ReplanReason.PERMISSION_BLOCKED,
                attempt=1,
            )
        )
        self.assertEqual(decision.action, ReplanAction.ESCALATE_MAIN_AGENT)


if __name__ == "__main__":
    unittest.main()

