from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cost_router.backends.codex_subagent import CodexSubagentBackend, parse_codex_output
from cost_router.backends.external_cli import (
    _collect_patch_proposal,
    claude_cli_backend,
    parse_external_cli_output,
)
from cost_router.config.providers import provider_from_env
from cost_router.memory import MemoryStore
from cost_router.router import route_task
from cost_router.core.contracts import (
    DataClassification,
    Difficulty,
    ExternalPolicy,
    Risk,
    RouteDecision,
    Task,
    TaskConstraints,
    TaskMode,
    TokenAnalysis,
    TokenUsage,
)
from cost_router.usage import extract_token_usage
from cost_router.usage import estimate_delegation_savings
from cost_router.verifier import verify_worker_result


class CostRouterCoreTests(unittest.TestCase):
    def test_configured_claude_worker_uses_model_alias(self):
        from argparse import Namespace
        import json
        from cost_router.cli import resolve_worker_selection
        from cost_router.config.workers import builtin_workers

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workers.json"
            document = {"version": 1, "workers": builtin_workers()}
            document["workers"][0]["model"] = "mimo-v2.5-pro"
            document["workers"][0]["model_alias"] = "opus"
            from cost_router.config.workers import WorkerManifestStore
            store = WorkerManifestStore(path)
            baseline = store.load_document()
            store.save(document, expected_revision=baseline["revision"])
            args = Namespace(
                worker_id="claude-cli-sonnet", workers=str(path),
                backend="codex-subagent", claude_model=None,
            )
            selected = resolve_worker_selection(args)
            self.assertEqual(selected.model, "mimo-v2.5-pro")
            self.assertEqual(args.backend, "claude-cli")
            self.assertEqual(args.claude_model, "opus")

    def test_external_policy_requires_explicit_private_transfer_authorization(self):
        from cost_router.cli import build_parser, external_policy_error, external_transfer_error

        parser = build_parser()
        private_args = parser.parse_args(
            ["run", "--backend", "claude-cli", "--goal", "review code", "--execute"]
        )
        self.assertIn("explicit user authorization", external_policy_error(private_args) or "")

        allowed_args = parser.parse_args(
            [
                "run", "--backend", "claude-cli", "--goal", "review code", "--execute",
                "--external-policy", "allow",
            ]
        )
        self.assertIsNone(external_policy_error(allowed_args))

        public_args = parser.parse_args(
            [
                "run", "--backend", "claude-cli", "--goal", "review public example",
                "--execute", "--data-classification", "public",
            ]
        )
        self.assertIsNone(external_policy_error(public_args))
        self.assertIn(
            "explicit user authorization",
            external_transfer_error("claude-cli", "ask", "private") or "",
        )
        self.assertIsNone(external_transfer_error("none", "never", "private"))

    def test_external_policy_is_serialized_and_staged_for_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Task(
                goal="review bounded private code",
                constraints=TaskConstraints(
                    external_policy=ExternalPolicy.ALLOW,
                    data_classification=DataClassification.PRIVATE,
                ),
            )
            self.assertEqual(task.to_dict()["constraints"]["external_policy"], "allow")
            backend = claude_cli_backend(work_dir=Path(tmp) / ".cost-router")
            _, _, prompt = backend.prepare(task)
            self.assertIn("external_policy=allow", prompt)
            self.assertIn("data_classification=private", prompt)

    def test_legacy_public_import_paths_survive_modular_refactor(self):
        from cost_router.analytics import AnalyticsStore
        from cost_router.async_tasks import AsyncTaskRuntime
        from cost_router.cli import memory_command
        from cost_router.paths import default_memory_path
        from cost_router.schemas import Task
        from cost_router.usage import estimate_token_count

        self.assertTrue(callable(default_memory_path))
        self.assertTrue(callable(estimate_token_count))
        self.assertTrue(callable(memory_command))
        self.assertIsNotNone(AnalyticsStore)
        self.assertIsNotNone(AsyncTaskRuntime)
        self.assertIsNotNone(Task)

    def setUp(self) -> None:
        os.environ["TEST_QWEN_BASE_URL"] = "http://example.invalid/v1"
        os.environ["TEST_QWEN_MODEL"] = "Qwen3.5-9B-AWQ"
        os.environ["TEST_QWEN_API_KEY"] = "test-key"

    def provider(self):
        return provider_from_env(
            provider_id="qwen_vllm",
            name="Qwen test provider",
            base_url_env="TEST_QWEN_BASE_URL",
            model_env="TEST_QWEN_MODEL",
            api_key_env="TEST_QWEN_API_KEY",
        )

    def test_route_log_task_to_codex_subagent(self) -> None:
        task = Task(goal="analyze failure log", paths=[Path("train.log")])
        decision = route_task(task, self.provider(), "qwen_explorer")
        self.assertTrue(decision.can_delegate)
        self.assertEqual(decision.backend, "codex_subagent")
        self.assertEqual(decision.worker, "qwen_explorer")

    def test_prepare_codex_subagent_command_without_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "train.log"
            log_path.write_text("ERROR cuda out of memory\n", encoding="utf-8")
            task = Task(goal="analyze failure log", repo=Path(tmp), paths=[log_path])
            backend = CodexSubagentBackend(
                provider=self.provider(),
                worker_name="qwen_explorer",
                work_dir=Path(tmp) / ".cost-router",
            )
            agent_file, output_file, command, prompt = backend.prepare(task)
            command_text = "\n".join(command)
            self.assertTrue(agent_file.exists())
            self.assertIn('model_provider = "qwen_vllm"', agent_file.read_text(encoding="utf-8"))
            self.assertIn('env_key="TEST_QWEN_API_KEY"', command_text)
            self.assertNotIn("test-key", command_text)
            self.assertIn(str(output_file.resolve()), command_text)
            self.assertIn(str(log_path), prompt)

    def test_prepare_claude_cli_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "train.log"
            log_path.write_text("ERROR cuda out of memory\n", encoding="utf-8")
            context_pack = Path(tmp) / "context.md"
            context_pack.write_text("Training run context\n", encoding="utf-8")
            task = Task(
                goal="analyze failure log",
                repo=Path(tmp),
                paths=[log_path],
                context_packs=[context_pack],
            )
            backend = claude_cli_backend(
                command="claude",
                model="sonnet-test",
                work_dir=Path(tmp) / ".cost-router",
            )
            output_file, command, prompt = backend.prepare(task)
            self.assertEqual(command[:4], ["claude", "-p", "--output-format", "json"])
            self.assertIn("--safe-mode", command)
            self.assertIn("--permission-mode", command)
            self.assertIn("dontAsk", command)
            self.assertIn("--strict-mcp-config", command)
            self.assertIn("--tools", command)
            self.assertIn("Read,Grep,Glob", command)
            self.assertIn("--model", command)
            self.assertIn("sonnet-test", command)
            self.assertNotIn(str(log_path), prompt)
            self.assertIn("path/001_train.log", prompt)
            self.assertIn("context_pack/001_context.md", prompt)
            workspace = output_file.parent / "workspace"
            self.assertEqual(
                (workspace / "path" / "001_train.log").read_text(encoding="utf-8"),
                "ERROR cuda out of memory\n",
            )
            self.assertEqual(
                (workspace / "context_pack" / "001_context.md").read_text(encoding="utf-8"),
                "Training run context\n",
            )
            self.assertTrue((workspace / "MANIFEST.md").exists())
            self.assertEqual(output_file.name, "claude_cli-output.md")

    def test_claude_patch_proposal_changes_only_staged_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            source = repo / "example.py"
            source.write_text("value = 1\n", encoding="utf-8")
            task = Task(
                goal="change the value to two",
                repo=repo,
                write_paths=[source],
                constraints=TaskConstraints(mode=TaskMode.PATCH),
            )
            backend = claude_cli_backend(work_dir=Path(tmp) / ".cost-router")
            output_file, command, prompt = backend.prepare(task)

            self.assertIn("acceptEdits", command)
            self.assertIn("Read,Grep,Glob,Edit,Write", command)
            self.assertIn("write_path/001_example.py", prompt)
            self.assertNotIn(str(source), prompt)

            workspace = output_file.parent / "workspace"
            staged = workspace / "write_path" / "001_example.py"
            staged.write_text("value = 2\n", encoding="utf-8")
            proposal = _collect_patch_proposal(task, workspace, output_file.parent)

            self.assertEqual(source.read_text(encoding="utf-8"), "value = 1\n")
            self.assertEqual(proposal.changed_paths, ["example.py"])
            self.assertFalse(proposal.policy_violations)
            self.assertIsNotNone(proposal.path)
            assert proposal.path is not None
            patch = proposal.path.read_text(encoding="utf-8")
            self.assertIn("--- a/example.py", patch)
            self.assertIn("+++ b/example.py", patch)
            self.assertIn("+value = 2", patch)

            output_file.write_text("worker output", encoding="utf-8")
            result = parse_external_cli_output(
                """
## Summary
Changed the configured value.
## Evidence
- example.py now uses value 2.
## Risks
- Tests were not run.
## Next Steps
- Apply the proposal and run tests.
""",
                output_file,
            )
            result.proposed_patch_path = proposal.path
            result.changed_paths = proposal.changed_paths
            result.policy_violations = proposal.policy_violations
            verification = verify_worker_result(result, repo, task)
            self.assertTrue(verification.accepted)
            store = MemoryStore(Path(tmp) / "patch-memory.sqlite3")
            store.record_subtask(
                task=task,
                decision=RouteDecision(
                    difficulty=Difficulty.MEDIUM,
                    risk=Risk.PATCH,
                    can_delegate=True,
                    backend="claude_cli",
                    worker="claude_cli",
                    model="test",
                    reason="test patch proposal",
                ),
                result=result,
                verification=verification,
            )
            edges = store.recent_graph_edges()
            self.assertTrue(any(edge["edge_type"] == "may_write" for edge in edges))
            self.assertTrue(any(edge["edge_type"] == "proposes_patch" for edge in edges))

    def test_claude_patch_proposal_rejects_out_of_scope_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            source = repo / "example.py"
            source.write_text("value = 1\n", encoding="utf-8")
            task = Task(
                goal="change the value",
                repo=repo,
                write_paths=[source],
                constraints=TaskConstraints(mode=TaskMode.PATCH),
            )
            backend = claude_cli_backend(work_dir=Path(tmp) / ".cost-router")
            output_file, _, _ = backend.prepare(task)
            workspace = output_file.parent / "workspace"
            (workspace / "write_path" / "001_example.py").write_text(
                "value = 2\n", encoding="utf-8"
            )
            (workspace / "MANIFEST.md").write_text("tampered\n", encoding="utf-8")

            proposal = _collect_patch_proposal(task, workspace, output_file.parent)
            self.assertTrue(proposal.policy_violations)
            self.assertIn("MANIFEST.md", proposal.policy_violations[0])

    def test_parse_and_verify_codex_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "codex-output.md"
            output_file.write_text("placeholder\n", encoding="utf-8")
            result = parse_codex_output(
                """
## Summary
Evaluation failed due to CUDA OOM.
## Evidence
- train.log contains CUDA out of memory.
## Risks
- Log may be incomplete.
## Next Steps
- Reduce eval batch size.
""",
                output_file,
            )
            verification = verify_worker_result(result, Path(tmp))
            self.assertTrue(verification.accepted)
            self.assertEqual(result.status, "success")
            self.assertTrue(result.next_steps)

    def test_parse_claude_heading_style_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "claude-output.md"
            output_file.write_text("placeholder\n", encoding="utf-8")
            result = parse_external_cli_output(
                """
## SkillOpt Failure Log Analysis

### Summary
Evaluation failed during eval due to CUDA OOM.

### Evidence
- train.log reports CUDA out of memory.

### Risks
- Resume may fail again with the same eval settings.

### Next Steps
1. Reduce eval batch size.
""",
                output_file,
            )
            verification = verify_worker_result(result, Path(tmp))
            self.assertTrue(verification.accepted)
            self.assertIn("CUDA OOM", result.summary)
            self.assertTrue(result.evidence)
            self.assertTrue(result.next_steps)

    def test_parse_claude_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "claude-output.md"
            output_file.write_text("placeholder\n", encoding="utf-8")
            result = parse_external_cli_output(
                """
{"type":"result","result":"## Summary\\nEval failed due to CUDA OOM.\\n## Evidence\\n- train.log shows OOM.\\n## Risks\\n- May recur.\\n## Next Steps\\n- Reduce eval batch size.","usage":{"input_tokens":10,"output_tokens":5}}
""",
                output_file,
            )
            verification = verify_worker_result(result, Path(tmp))
            self.assertTrue(verification.accepted)
            self.assertEqual(result.token_usage.total_tokens, 15)

    def test_memory_records_run_and_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "memory.sqlite3"
            context_pack = Path(tmp) / "context.md"
            context_pack.write_text("Project context\n", encoding="utf-8")
            task = Task(goal="analyze failure log", repo=Path(tmp), context_packs=[context_pack])
            decision = route_task(task, self.provider(), "qwen_explorer")
            result = parse_codex_output(
                """
## Summary
Evaluation failed due to CUDA OOM.
## Evidence
- codex output has the finding.
## Risks
- none
## Next Steps
- check GPU memory
""",
                Path(tmp) / "codex-output.md",
            )
            result.token_usage = TokenUsage(total_tokens=321, source="test")
            result.token_analysis = TokenAnalysis(
                delegated_context_tokens_estimate=1000,
                returned_result_tokens_estimate=100,
                estimated_main_tokens_saved=900,
            )
            (Path(tmp) / "codex-output.md").write_text("x", encoding="utf-8")
            verification = verify_worker_result(result, Path(tmp))
            store = MemoryStore(db)
            store.record_subtask(
                task=task,
                decision=decision,
                result=result,
                verification=verification,
            )
            self.assertTrue(db.exists())
            self.assertEqual(len(store.recent_runs()), 1)
            self.assertEqual(len(store.recent_subtasks()), 1)
            self.assertEqual(len(store.recent_facts()), 1)
            subtask = store.recent_subtasks()[0]
            self.assertEqual(subtask["token_usage"]["total_tokens"], 321)
            self.assertEqual(subtask["token_analysis"]["estimated_main_tokens_saved"], 900)
            summary = store.token_summary()
            self.assertEqual(summary["subtasks_with_results"], 1)
            self.assertEqual(summary["actual_worker_tokens"], 321)
            self.assertEqual(summary["estimated_main_tokens_saved"], 900)
            graph = store.graph_summary()
            self.assertEqual(graph["nodes_worker_task"], 1)
            self.assertEqual(graph["nodes_control"], 1)
            self.assertEqual(graph["nodes_context_pack"], 1)
            self.assertGreaterEqual(graph["nodes_artifact"], 1)
            self.assertEqual(graph["edges_delegates_to"], 1)
            self.assertEqual(graph["edges_uses_context"], 1)
            self.assertGreaterEqual(graph["edges_evidence_for"], 1)
            self.assertGreaterEqual(graph["worker_events"], 2)
            nodes = store.recent_graph_nodes()
            self.assertTrue(any(node["kind"] == "worker_task" for node in nodes))
            events = store.recent_worker_events()
            self.assertTrue(any(event["event_type"] == "final" for event in events))
            self.assertTrue(any(event["event_type"] == "proposed_fact" for event in events))

    def test_extract_codex_token_footer(self) -> None:
        usage = extract_token_usage("some output\n\ntokens used\n28,145\n")
        self.assertEqual(usage.total_tokens, 28145)
        self.assertEqual(usage.source, "codex_footer")

    def test_extract_json_token_usage(self) -> None:
        usage = extract_token_usage('{"usage":{"input_tokens":10,"output_tokens":5}}')
        self.assertEqual(usage.input_tokens, 10)
        self.assertEqual(usage.output_tokens, 5)
        self.assertEqual(usage.total_tokens, 15)

    def test_estimate_delegation_savings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "train.log"
            log_path.write_text("x" * 400, encoding="utf-8")
            task = Task(goal="analyze log", paths=[log_path])
            analysis = estimate_delegation_savings(task)
            self.assertGreaterEqual(analysis.delegated_context_tokens_estimate or 0, 100)


if __name__ == "__main__":
    unittest.main()
