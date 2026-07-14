from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..config.providers import ConfigError, load_env_file, provider_from_env
from ..core.contracts import (
    DataClassification,
    ExternalPolicy,
    Task,
    TaskConstraints,
    TaskMode,
)
from ..delegator.backends.codex_subagent import CodexSubagentBackend
from ..delegator.backends.external_cli import claude_cli_backend
from ..delegator.runtime import DelegationRuntime, PreparedWorker
from ..memory import MemoryStore
from ..config.paths import default_memory_path
from ..router import route_task
from ..usage import estimate_delegation_savings


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args)
    if args.command == "decompose":
        return decompose_command(args)
    if args.command == "graph-run":
        return graph_run_command(args)
    if args.command == "memory":
        return memory_command(args)
    if args.command == "dashboard":
        return dashboard_command(args)
    if args.command == "setup":
        return setup_command(args)
    if args.command == "async-task":
        return async_task_command(args)
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="c4harness")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Route a read-only coding task")
    run.add_argument("--goal", required=True, help="Task goal")
    run.add_argument("--path", action="append", default=[], help="Path to inspect; repeatable")
    run.add_argument(
        "--write-path",
        action="append",
        default=[],
        help="Path the worker may modify in patch mode; repeatable",
    )
    run.add_argument(
        "--context-pack",
        action="append",
        default=[],
        help="Worker-readable background context pack path; repeatable",
    )
    run.add_argument("--repo", default=".", help="Repository/work directory")
    run.add_argument(
        "--mode",
        choices=["read-only", "patch"],
        default="read-only",
        help="Delegate read-only analysis or an isolated patch proposal",
    )
    run.add_argument("--env-file", default=".env", help="Env file to load")
    run.add_argument("--provider-id", default="qwen_vllm")
    run.add_argument("--provider-name", default="Qwen vLLM Responses endpoint")
    run.add_argument("--base-url-env", default="QWEN_CHAT_BASE_URL")
    run.add_argument("--model-env", default="QWEN_CHAT_MODEL")
    run.add_argument("--api-key-env", default="QWEN_CHAT_API_KEY")
    run.add_argument("--worker", default="qwen_explorer")
    run.add_argument(
        "--parent-task-label",
        default=None,
        help="Human-readable parent task shared by related delegated calls",
    )
    run.add_argument(
        "--backend",
        choices=["codex-subagent", "claude-cli"],
        default="codex-subagent",
        help="Worker backend to use",
    )
    run.add_argument("--claude-command", default="claude", help="Claude CLI command path")
    run.add_argument("--claude-model", default=None, help="Optional Claude CLI model")
    run.add_argument("--worker-id", default=None, help="Select a configured Worker manifest entry")
    run.add_argument("--workers", default=None, help="Override the Worker manifest path")
    run.add_argument(
        "--external-policy",
        choices=[item.value for item in ExternalPolicy],
        default=ExternalPolicy.ASK.value,
        help="External transfer policy: never, ask, or explicitly user-authorized allow",
    )
    run.add_argument(
        "--data-classification",
        choices=[item.value for item in DataClassification],
        default=DataClassification.PRIVATE.value,
        help="Classification of content staged for the external worker",
    )
    run.add_argument("--memory", default=str(default_memory_path()))
    run.add_argument("--execute", action="store_true", help="Actually invoke the worker backend")
    run.add_argument("--json", action="store_true", help="Print JSON output")

    decompose = subparsers.add_parser("decompose", help="Preview a task contract graph")
    decompose_source = decompose.add_mutually_exclusive_group(required=True)
    decompose_source.add_argument("--goal", help="Legacy goal-based preview input")
    decompose_source.add_argument(
        "--plan-file",
        help="Codex-authored task proposal JSON to validate, compile, and assign",
    )
    decompose.add_argument("--repo", default=".")
    decompose.add_argument("--path", action="append", default=[])
    decompose.add_argument("--context-pack", action="append", default=[])
    decompose.add_argument("--write-path", action="append", default=[])
    decompose.add_argument("--requirement", action="append", default=[])
    decompose.add_argument("--constraint", action="append", default=[])
    decompose.add_argument("--acceptance", action="append", default=[])
    decompose.add_argument("--active-skill", action="append", default=[])
    decompose.add_argument("--skill-step", action="append", default=[])
    decompose.add_argument("--environment-fact", action="append", default=[])
    decompose.add_argument("--unresolved-question", action="append", default=[])
    decompose.add_argument("--plan-mode", action="store_true")
    decompose.add_argument("--workers", default=None)
    decompose.add_argument("--memory", default=str(default_memory_path()))
    decompose.add_argument("--json", action="store_true")

    # -- graph-run: compile a proposal and execute through GraphExecutionService ----
    graph_run = subparsers.add_parser(
        "graph-run",
        help="Compile a Codex proposal and execute the task contract graph",
    )
    graph_run.add_argument(
        "--plan-file",
        required=True,
        help="Codex-authored task proposal JSON",
    )
    graph_run.add_argument("--repo", default=".", help="Repository/work directory")
    graph_run.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke worker backends (default: dry-run)",
    )
    graph_run.add_argument(
        "--max-parallel",
        type=int,
        default=1,
        help="Maximum concurrent nodes (default 1; >1 enables bounded parallelism)",
    )
    graph_run.add_argument("--workers", default=None, help="Override the Worker manifest path")
    graph_run.add_argument("--memory", default=str(default_memory_path()))
    graph_run.add_argument(
        "--parent-task-label",
        default=None,
        help="Shared ledger label for all node calls in this graph run",
    )
    graph_run.add_argument("--json", action="store_true", help="Print JSON output")
    graph_run.add_argument("--env-file", default=".env", help="Env file to load")
    graph_run.add_argument("--provider-id", default="qwen_vllm")
    graph_run.add_argument("--provider-name", default="Qwen vLLM Responses endpoint")
    graph_run.add_argument("--base-url-env", default="QWEN_CHAT_BASE_URL")
    graph_run.add_argument("--model-env", default="QWEN_CHAT_MODEL")
    graph_run.add_argument("--api-key-env", default="QWEN_CHAT_API_KEY")
    graph_run.add_argument("--claude-command", default="claude")
    graph_run.add_argument(
        "--external-policy",
        choices=[item.value for item in ExternalPolicy],
        default=ExternalPolicy.ASK.value,
    )
    graph_run.add_argument(
        "--data-classification",
        choices=[item.value for item in DataClassification],
        default=DataClassification.PRIVATE.value,
    )
    graph_run.add_argument(
        "--integration-dir",
        default=None,
        help="Parent directory for integration workspaces (default: <repo>/.c4harness/graph-runs)",
    )

    memory = subparsers.add_parser("memory", help="Inspect local memory/ledger")
    memory.add_argument("--memory", default=str(default_memory_path()))
    memory.add_argument("--limit", type=int, default=10)
    memory.add_argument("--json", action="store_true", help="Print JSON output")

    dashboard = subparsers.add_parser("dashboard", help="Open the local routing dashboard")
    dashboard.add_argument("--memory", default=str(default_memory_path()))
    dashboard.add_argument("--host", default="127.0.0.1", help="Address to listen on")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--no-open", action="store_true", help="Do not open a browser")

    setup = subparsers.add_parser("setup", help="Initialize global storage and user skill")
    setup.add_argument("--force", action="store_true", help="Replace an existing user skill")
    setup.add_argument("--json", action="store_true", help="Print JSON output")

    async_task = subparsers.add_parser(
        "async-task", help="Run and monitor a workload in the background"
    )
    async_subparsers = async_task.add_subparsers(dest="async_command")
    async_start = async_subparsers.add_parser("start", help="Start an asynchronous task")
    async_start.add_argument("--goal", required=True, help="Outcome the worker should monitor")
    async_start.add_argument("--repo", default=".", help="Workload working directory")
    async_start.add_argument(
        "--command",
        dest="workload_command",
        required=True,
        help="Workload command parsed without a shell, for example: 'bash scripts/run.sh'",
    )
    async_start.add_argument(
        "--log-path", action="append", default=[], help="Additional live log path; repeatable"
    )
    async_start.add_argument(
        "--backend", choices=["claude-cli", "none"], default="claude-cli"
    )
    async_start.add_argument("--claude-command", default="claude")
    async_start.add_argument("--claude-model", default=None)
    async_start.add_argument("--worker-id", default=None, help="Select a configured Claude Worker")
    async_start.add_argument("--workers", default=None, help="Override the Worker manifest path")
    async_start.add_argument(
        "--external-policy",
        choices=[item.value for item in ExternalPolicy],
        default=ExternalPolicy.ASK.value,
    )
    async_start.add_argument(
        "--data-classification",
        choices=[item.value for item in DataClassification],
        default=DataClassification.PRIVATE.value,
    )
    async_start.add_argument(
        "--thread-id",
        default=None,
        help="Associate the task with a Codex thread; defaults to CODEX_THREAD_ID",
    )
    async_start.add_argument("--interval", type=float, default=60.0)
    async_start.add_argument("--max-runtime", type=int, default=None)
    async_start.add_argument("--success-file", default=None)
    async_start.add_argument("--failure-file", default=None)
    async_start.add_argument("--memory", default=str(default_memory_path()))
    async_start.add_argument(
        "--foreground", action="store_true", help="Run the async runtime in this process"
    )
    async_start.add_argument("--json", action="store_true", help="Print JSON output")

    async_status = async_subparsers.add_parser("status", help="Show one asynchronous task")
    async_status.add_argument("task_id")
    async_status.add_argument("--memory", default=str(default_memory_path()))
    async_status.add_argument("--json", action="store_true")

    async_list = async_subparsers.add_parser("list", help="List asynchronous tasks")
    async_list.add_argument("--memory", default=str(default_memory_path()))
    async_list.add_argument("--limit", type=int, default=20)
    async_list.add_argument("--json", action="store_true")

    async_events = async_subparsers.add_parser("events", help="Show task events")
    async_events.add_argument("task_id")
    async_events.add_argument("--memory", default=str(default_memory_path()))
    async_events.add_argument("--limit", type=int, default=100)
    async_events.add_argument("--json", action="store_true")

    async_stop = async_subparsers.add_parser("stop", help="Request task cancellation")
    async_stop.add_argument("task_id")
    async_stop.add_argument("--memory", default=str(default_memory_path()))

    async_inbox = async_subparsers.add_parser(
        "inbox", help="List durable asynchronous events awaiting attention"
    )
    async_inbox.add_argument("--memory", default=str(default_memory_path()))
    async_inbox.add_argument("--limit", type=int, default=50)
    async_inbox.add_argument("--unread-only", action="store_true")
    async_inbox.add_argument("--thread-id", default=None)
    async_inbox.add_argument("--json", action="store_true")

    async_ack = async_subparsers.add_parser(
        "ack", help="Acknowledge one durable asynchronous inbox item"
    )
    async_ack.add_argument("inbox_id", type=int)
    async_ack.add_argument("--memory", default=str(default_memory_path()))

    return parser


def decompose_command(args: argparse.Namespace) -> int:
    from ..config.workers import WorkerManifestStore
    from ..decompose import (
        AcceptanceCriterion,
        CodexTaskProposal,
        DecompositionPlanner,
        InteractionMode,
        Requirement,
        RequirementKind,
        TaskSituationBuilder,
        WorkerRegistry,
        compile_proposal,
    )
    from ..decompose import ProposalCompileError, ProposalParseError
    from ..history import PlanSnapshot, SQLiteHistoryRepository, build_capability_profile

    repo = Path(args.repo).resolve()
    manifest_store = WorkerManifestStore(Path(args.workers).expanduser() if args.workers else None)
    workers, preferences = manifest_store.registry()
    registry = WorkerRegistry(workers)
    history = SQLiteHistoryRepository(Path(args.memory).expanduser())
    profiles = {
        worker_id: build_capability_profile(worker_id, history.outcomes_for_worker(worker_id))
        for worker_id in workers
    }
    try:
        if args.plan_file:
            plan_path = Path(args.plan_file).expanduser()
            if not plan_path.is_absolute():
                plan_path = repo / plan_path
            proposal = CodexTaskProposal.from_json(
                plan_path.read_text(encoding="utf-8")
            )
            plan = compile_proposal(
                proposal,
                repo,
                registry,
                worker_preferences=preferences,
                capability_profiles=profiles,
            )
        else:
            write_paths = [_resolve_from_repo(repo, item) for item in args.write_path]
            task = Task(
                goal=args.goal,
                repo=repo,
                paths=[_resolve_from_repo(repo, item) for item in args.path],
                write_paths=write_paths,
                context_packs=[_resolve_from_repo(repo, item) for item in args.context_pack],
                constraints=TaskConstraints(
                    mode=TaskMode.PATCH if write_paths else TaskMode.READ_ONLY
                ),
            )
            deliverables = list(args.requirement) or [args.goal]
            requirements = [
                *[
                    Requirement(f"R{index}", text, RequirementKind.DELIVERABLE)
                    for index, text in enumerate(deliverables, 1)
                ],
                *[
                    Requirement(f"C{index}", text, RequirementKind.CONSTRAINT)
                    for index, text in enumerate(args.constraint, 1)
                ],
            ]
            required_refs = tuple(item.id for item in requirements if item.required)
            criteria = [
                AcceptanceCriterion(f"A{index}", text, requirement_refs=required_refs)
                for index, text in enumerate(args.acceptance, 1)
            ] or None
            builder = TaskSituationBuilder()
            situation = builder.from_task(
                task,
                requirements=requirements,
                acceptance_criteria=criteria,
                interaction_mode=(
                    InteractionMode.PLAN if args.plan_mode else InteractionMode.EXECUTE
                ),
                active_skills=args.active_skill,
                skill_steps=args.skill_step,
                environment_facts=args.environment_fact,
                unresolved_questions=args.unresolved_question,
                workers=workers.values(),
                historical_profile_summary=[
                    f"{worker_id}:samples={sum(item.usable_sample_count for item in profile.evidence)}"
                    for worker_id, profile in profiles.items()
                ],
            )
            planner = DecompositionPlanner(
                worker_preferences=preferences,
                capability_profiles=profiles,
            )
            plan = planner.plan(task, situation, registry)
    except (OSError, ProposalParseError, ProposalCompileError, ValueError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2))
        else:
            print(f"decompose error: {error}")
        return 2
    history.append_plan(PlanSnapshot.from_plan(plan))
    payload = plan.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"C4 Decomposition: {payload['shape']}")
        for node in payload["graph"]["nodes"]:
            print(f"- {node['kind']} {node['id']}: {node['objective']} -> {node['assigned_worker_id']}")
        for reason in payload["reasons"]:
            print(f"  reason: {reason}")
    return 0


def graph_run_command(args: argparse.Namespace) -> int:
    """Compile a Codex proposal and execute through GraphExecutionService."""
    from ..config.workers import WorkerManifestStore
    from ..decompose import (
        CodexTaskProposal,
        WorkerRegistry,
        compile_proposal,
        ProposalCompileError,
        ProposalParseError,
    )
    from ..history import SQLiteHistoryRepository, build_capability_profile
    from ..application.run_graph import GraphExecutionService

    repo = Path(args.repo).resolve()
    manifest_store = WorkerManifestStore(
        Path(args.workers).expanduser() if args.workers else None
    )
    workers, preferences = manifest_store.registry()
    registry = WorkerRegistry(workers)
    history = SQLiteHistoryRepository(Path(args.memory).expanduser())
    profiles = {
        worker_id: build_capability_profile(
            worker_id, history.outcomes_for_worker(worker_id)
        )
        for worker_id in workers
    }

    # -- compile proposal ----------------------------------------------------
    try:
        plan_path = Path(args.plan_file).expanduser()
        if not plan_path.is_absolute():
            plan_path = repo / plan_path
        proposal = CodexTaskProposal.from_json(
            plan_path.read_text(encoding="utf-8")
        )
        plan = compile_proposal(
            proposal,
            repo,
            registry,
            worker_preferences=preferences,
            capability_profiles=profiles,
        )
    except (OSError, ProposalParseError, ProposalCompileError, ValueError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2))
        else:
            print(f"graph-run error: {error}")
        return 2

    # -- validate max-parallel -----------------------------------------------
    if args.max_parallel < 1:
        msg = "--max-parallel must be at least 1"
        if args.json:
            print(json.dumps({"error": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"graph-run error: {msg}")
        return 2

    # -- set up execution infrastructure ------------------------------------
    # Dry-run compiles and schedules contracts only.  It must not require
    # provider credentials or mutate backend selection state.
    if args.execute:
        load_env_file_if_exists(Path(args.env_file))

    base_task = Task(
        goal=plan.situation.objective,
        repo=repo,
        parent_task_label=args.parent_task_label,
        constraints=TaskConstraints(
            external_policy=ExternalPolicy(args.external_policy),
            data_classification=DataClassification(args.data_classification),
        ),
    )

    runtime = DelegationRuntime(MemoryStore(Path(args.memory)))

    # The compiled plan owns worker selection.  The CLI only materializes the
    # assigned/fallback Worker arms into backend adapters.
    primary_worker_ids = {
        node.assigned_worker_id
        for node in plan.graph.nodes.values()
        if node.assigned_worker_id
    }
    execution_worker_ids = _graph_execution_worker_ids(plan)
    try:
        execution_workers = {worker_id: workers[worker_id] for worker_id in execution_worker_ids}
    except KeyError as error:
        message = f"assigned Worker is missing from the manifest: {error.args[0]}"
        if args.json:
            print(json.dumps({"error": message}, ensure_ascii=False, indent=2))
        else:
            print(f"graph-run config error: {message}")
        return 2

    unsupported = sorted(
        worker.id
        for worker in execution_workers.values()
        if worker.id in primary_worker_ids
        and worker.backend not in {"claude_cli", "codex_subagent"}
    )
    if args.execute and unsupported:
        message = "unsupported graph Worker backend(s): " + ", ".join(unsupported)
        if args.json:
            print(json.dumps({"error": message}, ensure_ascii=False, indent=2))
        else:
            print(f"graph-run config error: {message}")
        return 2

    needs_claude = any(worker.backend == "claude_cli" for worker in execution_workers.values())
    needs_codex = any(worker.backend == "codex_subagent" for worker in execution_workers.values())
    needs_codex_primary = any(
        worker.id in primary_worker_ids and worker.backend == "codex_subagent"
        for worker in execution_workers.values()
    )
    if args.execute and needs_claude:
        policy_error = external_transfer_error(
            "claude-cli", args.external_policy, args.data_classification
        )
        if policy_error:
            if args.json:
                print(json.dumps({"error": policy_error}, ensure_ascii=False, indent=2))
            else:
                print(f"graph-run config error: {policy_error}")
            return 2

    provider = None
    if args.execute and needs_codex:
        try:
            provider = provider_from_env(
                provider_id=args.provider_id,
                name=args.provider_name,
                base_url_env=args.base_url_env,
                model_env=args.model_env,
                api_key_env=args.api_key_env,
            )
        except ConfigError as error:
            if not needs_codex_primary:
                provider = None
            else:
                if args.json:
                    print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2))
                else:
                    print(f"graph-run config error: {error}")
                return 2
        except OSError as error:
            if not needs_codex_primary:
                provider = None
            else:
                if args.json:
                    print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2))
                else:
                    print(f"graph-run config error: {error}")
                return 2

    def worker_for(node):
        worker_id = node.assigned_worker_id
        if not worker_id or worker_id not in workers:
            raise ValueError(f"node {node.id} has no executable assigned Worker")
        return workers[worker_id]

    def decide(node, task):
        return _graph_route_decision(worker_for(node), task)

    def prepare(node, task):
        worker = worker_for(node)
        if worker.backend == "claude_cli":
            backend = claude_cli_backend(
                command=args.claude_command,
                model=worker.model_alias or worker.model,
            )
            output_file, command, prompt = backend.prepare(task)
            return PreparedWorker(
                output_file=output_file,
                command=command,
                prompt=prompt,
                runner=backend.run_prepared,
            )
        if worker.backend == "codex_subagent":
            if provider is None:
                raise RuntimeError("Codex provider is unavailable in execute mode")
            backend = CodexSubagentBackend(provider=provider, worker_name=worker.id)
            agent_file, output_file, command, prompt = backend.prepare(task)
            return PreparedWorker(
                agent_file=agent_file,
                output_file=output_file,
                command=command,
                prompt=prompt,
                runner=backend.run_prepared,
            )
        raise ValueError(f"unsupported Worker backend: {worker.backend}")

    def fallback_worker(node, _attempt):
        candidates = plan.assignment_records.get(node.id, {}).get("candidates", [])
        ranked = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.get("eligible")
                and candidate.get("worker_id") != node.assigned_worker_id
                and candidate.get("worker_id") in workers
                and workers[str(candidate.get("worker_id"))].backend
                    in {"claude_cli", "codex_subagent"}
                and not (
                    workers[str(candidate.get("worker_id"))].backend == "codex_subagent"
                    and provider is None
                )
            ),
            key=lambda candidate: (
                -float(candidate.get("score", 0.0)),
                str(candidate.get("worker_id", "")),
            ),
        )
        return str(ranked[0]["worker_id"]) if ranked else None

    integration_dir = (
        Path(args.integration_dir).resolve() if args.integration_dir else None
    )

    service = GraphExecutionService(
        runtime,
        decide=decide,
        prepare=prepare,
        fallback_worker=fallback_worker,
        integration_parent_dir=integration_dir,
    )

    report = service.execute(
        plan,
        base_task,
        execute=args.execute,
        max_parallel=args.max_parallel,
    )

    payload = report.to_dict()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_graph_run_human(payload, args.execute)

    if not args.execute:
        return 0
    return 0 if report.accepted else 1


def _graph_execution_worker_ids(plan) -> set[str]:
    """Return primary and eligible fallback Worker ids referenced by a plan."""
    worker_ids = {
        node.assigned_worker_id
        for node in plan.graph.nodes.values()
        if node.assigned_worker_id
    }
    for record in plan.assignment_records.values():
        for candidate in record.get("candidates", []):
            if candidate.get("eligible") and candidate.get("worker_id"):
                worker_ids.add(str(candidate["worker_id"]))
    return worker_ids


def _graph_route_decision(worker, task: Task):
    from ..core.contracts import Difficulty, Risk, RouteDecision

    return RouteDecision(
        difficulty=Difficulty.MEDIUM,
        risk=Risk.PATCH if task.constraints.mode == TaskMode.PATCH else Risk.READ_ONLY,
        can_delegate=True,
        backend=worker.backend,
        worker=worker.id,
        model=worker.model_alias or worker.model,
        reason=f"Compiled graph assignment selected {worker.id} ({worker.harness}).",
    )


def _prepare_codex_for_graph(args, task, provider):
    backend = CodexSubagentBackend(provider=provider, worker_name=args.worker)
    agent_file, output_file, command, prompt = backend.prepare(task)
    return PreparedWorker(
        agent_file=agent_file,
        output_file=output_file,
        command=command,
        prompt=prompt,
        runner=backend.run_prepared,
    )


def _make_claude_decision_for_graph(args, task, selected_worker):
    from ..core.contracts import Difficulty, Risk, RouteDecision

    return RouteDecision(
        difficulty=Difficulty.MEDIUM,
        risk=Risk.PATCH,
        can_delegate=True,
        backend="claude_cli",
        worker=selected_worker.id if selected_worker else "claude_cli",
        model=selected_worker.model if selected_worker else (args.claude_model or "claude-default"),
        reason="Graph node delegated to Claude CLI external harness",
    )


def _print_graph_run_human(payload: dict, executed: bool) -> None:
    gr = payload.get("graph_result", {})
    print("Graph Execution")
    print("===============")
    print(f"Execution order: {gr.get('execution_order', [])}")
    print(f"All succeeded: {gr.get('all_succeeded')}")
    print(f"Has failures: {gr.get('has_failures')}")
    for nid, outcome in gr.get("node_outcomes", {}).items():
        state = outcome.get("state", "?")
        err = outcome.get("error")
        line = f"  {nid}: {state}"
        if err:
            line += f" ({err})"
        print(line)
    if not executed:
        print("Dry run only. Re-run with --execute to invoke worker backends.")


def run_command(args: argparse.Namespace) -> int:
    try:
        selected_worker = resolve_worker_selection(args)
    except ValueError as error:
        print(f"config error: {error}")
        return 2
    provider = None
    load_env_file_if_exists(Path(args.env_file))
    if args.backend == "codex-subagent":
        try:
            provider = provider_from_env(
                provider_id=args.provider_id,
                name=args.provider_name,
                base_url_env=args.base_url_env,
                model_env=args.model_env,
                api_key_env=args.api_key_env,
            )
        except ConfigError as error:
            print(f"config error: {error}")
            return 2

    repo = Path(args.repo).resolve()
    policy_error = external_policy_error(args)
    if policy_error:
        print(f"config error: {policy_error}")
        return 2
    mode = TaskMode.PATCH if args.mode == "patch" else TaskMode.READ_ONLY
    write_paths = [_resolve_from_repo(repo, item) for item in args.write_path]
    if mode == TaskMode.PATCH and not write_paths:
        print("config error: patch mode requires at least one --write-path")
        return 2
    if mode == TaskMode.PATCH and args.backend == "codex-subagent":
        print("config error: patch mode currently requires --backend claude-cli")
        return 2
    if any(not _is_within(path, repo) for path in write_paths):
        print("config error: every --write-path must be inside --repo")
        return 2
    task = Task(
        goal=args.goal,
        repo=repo,
        paths=[_resolve_from_repo(repo, item) for item in args.path],
        write_paths=write_paths,
        context_packs=[_resolve_from_repo(repo, item) for item in args.context_pack],
        constraints=TaskConstraints(
            mode=mode,
            external_policy=ExternalPolicy(args.external_policy),
            data_classification=DataClassification(args.data_classification),
        ),
        parent_task_label=args.parent_task_label,
    )
    runtime = DelegationRuntime(MemoryStore(Path(args.memory)))
    if args.backend == "codex-subagent":
        assert provider is not None
        decide = lambda current: route_task(current, provider, args.worker)
        prepare = lambda current: prepare_codex_backend(args, current, provider)
    else:
        decide = lambda current: make_claude_decision(args, current, selected_worker)
        prepare = lambda current: prepare_claude_backend(args, current)
    outcome = runtime.dispatch(
        task,
        decide=decide,
        prepare=prepare,
        execute=args.execute,
    )
    decision = outcome.decision
    prepared = outcome.prepared
    result = outcome.result
    verification = outcome.verification

    payload = {
        "task": task.to_dict(),
        "decision": decision.to_dict(),
        "prepared": prepared.public_dict(_redact_command(prepared.command, provider)),
        "executed": args.execute,
        "token_analysis_estimate": estimate_delegation_savings(task).to_dict(),
        "result": result.to_dict() if result else None,
        "verification": verification.to_dict() if verification else None,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return delegation_exit_code(args.execute, result, verification)


def delegation_exit_code(executed: bool, result, verification) -> int:
    """Return a shell-friendly status for one delegated worker invocation."""
    if not executed:
        return 0
    if result is None or result.status != "success":
        return 1
    if verification is None or not verification.accepted:
        return 1
    return 0


def load_env_file_if_exists(path: Path) -> None:
    if path.exists():
        load_env_file(path)


def external_policy_error(args: argparse.Namespace) -> str | None:
    if args.backend != "claude-cli" or not args.execute:
        return None
    return external_transfer_error(args.backend, args.external_policy, args.data_classification)


def external_transfer_error(
    backend: str, policy_value: str, classification_value: str
) -> str | None:
    if backend != "claude-cli":
        return None
    policy = ExternalPolicy(policy_value)
    classification = DataClassification(classification_value)
    if policy == ExternalPolicy.NEVER:
        return "Claude CLI is disabled by --external-policy never"
    if policy == ExternalPolicy.ASK and classification == DataClassification.PRIVATE:
        return (
            "private content requires explicit user authorization; after the user approves "
            "this bounded transfer, rerun with --external-policy allow"
        )
    return None


def prepare_codex_backend(args: argparse.Namespace, task: Task, provider):
    backend = CodexSubagentBackend(provider=provider, worker_name=args.worker)
    agent_file, output_file, command, prompt = backend.prepare(task)
    return PreparedWorker(
        agent_file=agent_file,
        output_file=output_file,
        command=command,
        prompt=prompt,
        runner=backend.run_prepared,
    )


def prepare_claude_backend(args: argparse.Namespace, task: Task):
    backend = claude_cli_backend(command=args.claude_command, model=args.claude_model)
    output_file, command, prompt = backend.prepare(task)
    return PreparedWorker(
        output_file=output_file,
        command=command,
        prompt=prompt,
        runner=backend.run_prepared,
    )


def make_claude_decision(args: argparse.Namespace, task: Task, selected_worker=None):
    from ..core.contracts import Difficulty, Risk, RouteDecision

    return RouteDecision(
        difficulty=Difficulty.MEDIUM if task.constraints.mode == TaskMode.PATCH else Difficulty.SIMPLE,
        risk=Risk.PATCH if task.constraints.mode == TaskMode.PATCH else Risk.READ_ONLY,
        can_delegate=True,
        backend="claude_cli",
        worker=selected_worker.id if selected_worker else "claude_cli",
        model=selected_worker.model if selected_worker else (args.claude_model or "claude-default"),
        reason=(
            "Patch proposal delegated to an isolated Claude CLI workspace"
            if task.constraints.mode == TaskMode.PATCH
            else "Read-only task delegated to Claude CLI external harness"
        )
        + (
            f"; external_policy={task.constraints.external_policy.value}, "
            f"data_classification={task.constraints.data_classification.value}."
        ),
    )


def resolve_worker_selection(args: argparse.Namespace):
    if not getattr(args, "worker_id", None):
        return None
    from ..config.workers import WorkerManifestStore

    path = Path(args.workers).expanduser() if getattr(args, "workers", None) else None
    workers, _ = WorkerManifestStore(path).registry()
    try:
        worker = workers[args.worker_id]
    except KeyError as error:
        raise ValueError(f"unknown Worker ID: {args.worker_id}") from error
    if not worker.enabled:
        raise ValueError(f"Worker is disabled: {worker.id}")
    if worker.backend != "claude_cli":
        raise ValueError(
            f"configured Worker execution currently supports claude_cli only: {worker.backend}"
        )
    args.backend = "claude-cli"
    args.claude_model = worker.model_alias or worker.model
    return worker


def _resolve_from_repo(repo: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def print_human(payload: dict) -> None:
    print("C4Harness")
    print("=========")
    print(f"Task: {payload['task']['goal']}")
    print(f"Decision: {payload['decision']['backend']} -> {payload['decision']['worker']}")
    print(f"Model: {payload['decision']['model']}")
    print(f"Reason: {payload['decision']['reason']}")
    print(f"Agent file: {payload['prepared']['agent_file']}")
    print(f"Output file: {payload['prepared']['output_file']}")
    if payload["executed"]:
        result = payload["result"] or {}
        verification = payload["verification"] or {}
        print(f"Result status: {result.get('status')}")
        print(f"Accepted: {verification.get('accepted')}")
        usage = result.get("token_usage") or {}
        if usage.get("total_tokens") is not None:
            print(f"Tokens: {usage.get('total_tokens')} ({usage.get('source')})")
        analysis = result.get("token_analysis") or {}
        print(
            "Token diversion estimate: "
            f"delegated={analysis.get('delegated_context_tokens_estimate')} "
            f"returned={analysis.get('returned_result_tokens_estimate')} "
            f"main_saved={analysis.get('estimated_main_tokens_saved')}"
        )
    else:
        print("Dry run only. Re-run with --execute to invoke the worker backend.")
        estimate = payload.get("token_analysis_estimate") or {}
        print(
            "Estimated delegated context tokens: "
            f"{estimate.get('delegated_context_tokens_estimate')}"
        )


def memory_command(args: argparse.Namespace) -> int:
    store = MemoryStore(Path(args.memory))
    payload = {
        "runs": store.recent_runs(args.limit),
        "subtasks": store.recent_subtasks(args.limit),
        "facts": store.recent_facts(args.limit),
        "token_summary": store.token_summary(),
        "graph_summary": store.graph_summary(),
        "graph_nodes": store.recent_graph_nodes(args.limit),
        "graph_edges": store.recent_graph_edges(args.limit),
        "worker_events": store.recent_worker_events(args.limit),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("C4Harness Memory")
        print("================")
        print("Runs")
        for run in payload["runs"]:
            print(f"- {run['id']} {run['created_at']} subtasks={run['subtask_count']} {run['goal']}")
        print("Subtasks")
        for subtask in payload["subtasks"]:
            print(
                f"- #{subtask['id']} run={subtask['run_id']} "
                f"{subtask['backend']}->{subtask['worker']} executed={subtask['executed']} "
                f"accepted={subtask['accepted']}"
            )
            usage = subtask.get("token_usage") or {}
            if usage.get("total_tokens") is not None:
                print(f"  tokens={usage.get('total_tokens')} source={usage.get('source')}")
            analysis = subtask.get("token_analysis") or {}
            if analysis.get("estimated_main_tokens_saved") is not None:
                print(
                    "  diversion="
                    f"delegated:{analysis.get('delegated_context_tokens_estimate')} "
                    f"returned:{analysis.get('returned_result_tokens_estimate')} "
                    f"main_saved:{analysis.get('estimated_main_tokens_saved')}"
                )
        print("Facts")
        for fact in payload["facts"]:
            print(f"- {fact['status']} run={fact['run_id']} {fact['fact']}")
        summary = payload["token_summary"]
        print("Token Diversion")
        print(f"- subtasks_with_results={summary['subtasks_with_results']}")
        print(f"- actual_worker_tokens={summary['actual_worker_tokens']}")
        print(
            "- delegated_context_tokens_estimate="
            f"{summary['delegated_context_tokens_estimate']}"
        )
        print(
            "- returned_result_tokens_estimate="
            f"{summary['returned_result_tokens_estimate']}"
        )
        print(
            "- estimated_main_tokens_saved="
            f"{summary['estimated_main_tokens_saved']}"
        )
        graph = payload["graph_summary"]
        print("Memory Graph")
        print(f"- nodes={graph['nodes']}")
        print(f"- edges={graph['edges']}")
        print(f"- worker_events={graph['worker_events']}")
        print(f"- file_locks={graph['file_locks']}")
        for node in payload["graph_nodes"]:
            print(
                f"- node {node['kind']} {node['status']} "
                f"id={node['id']} title={node['title']}"
            )
        for edge in payload["graph_edges"]:
            print(
                f"- edge {edge['edge_type']} "
                f"{edge['src_node_id']} -> {edge['dst_node_id']}"
            )
    return 0


def dashboard_command(args: argparse.Namespace) -> int:
    from ..dashboard.server import serve_dashboard

    serve_dashboard(
        Path(args.memory).expanduser(),
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
    )
    return 0


def setup_command(args: argparse.Namespace) -> int:
    from ..setup_user import setup_user

    payload = setup_user(force=args.force)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("C4Harness user setup")
        print("====================")
        print(f"Global ledger: {payload['memory_path']}")
        print(f"User skill: {payload['skill_path']} ({payload['skill_status']})")
        print("\nAdd this to ~/.codex/config.toml, then restart Codex:")
        print(payload["codex_config"])
        print("\nLaunch the console with: c4harness dashboard")
    return 0


def async_task_command(args: argparse.Namespace) -> int:
    from ..delegator.async_runtime import AsyncTaskConfig, AsyncTaskRuntime, AsyncTaskStore

    if not args.async_command:
        print(
            "usage: c4harness async-task "
            "{start,status,list,events,stop,inbox,ack}"
        )
        return 2
    memory_path = Path(args.memory).expanduser().resolve()
    store = AsyncTaskStore(memory_path)
    if args.async_command == "start":
        try:
            selected_worker = resolve_worker_selection(args)
        except ValueError as error:
            print(f"config error: {error}")
            return 2
        if selected_worker is not None and selected_worker.backend != "claude_cli":
            print("config error: async-task currently supports configured Claude CLI workers only")
            return 2
        policy_error = external_transfer_error(
            args.backend, args.external_policy, args.data_classification
        )
        if policy_error:
            print(f"config error: {policy_error}")
            return 2
        if args.interval <= 0:
            print("config error: --interval must be greater than zero")
            return 2
        workload_command = shlex.split(args.workload_command)
        if not workload_command:
            print("config error: --command cannot be empty")
            return 2
        repo = Path(args.repo).expanduser().resolve()
        thread_id = args.thread_id or os.environ.get("CODEX_THREAD_ID") or None
        config = AsyncTaskConfig(
            goal=args.goal,
            repo=repo,
            workload_command=workload_command,
            log_paths=[_resolve_from_repo(repo, item) for item in args.log_path],
            backend="claude_cli" if args.backend == "claude-cli" else "none",
            model=args.claude_model,
            interval_sec=args.interval,
            max_runtime_sec=args.max_runtime,
            success_file=_resolve_from_repo(repo, args.success_file) if args.success_file else None,
            failure_file=_resolve_from_repo(repo, args.failure_file) if args.failure_file else None,
            source_thread_id=thread_id,
            source_harness="codex" if thread_id else "cli",
            callback_mode="inbox",
            claude_command=args.claude_command,
            external_policy=args.external_policy,
            data_classification=args.data_classification,
        )
        store.create(config)
        if args.foreground:
            exit_code = AsyncTaskRuntime(memory_path, config.id).run()
            payload = _async_task_payload(store, config.id)
            _print_async_payload(payload, args.json)
            return exit_code
        runtime_dir = memory_path.parent / "async-tasks" / config.id
        runtime_dir.mkdir(parents=True, exist_ok=True)
        runtime_log = runtime_dir / "runtime.log"
        runtime_env = os.environ.copy()
        # ``PYTHONPATH`` must contain the parent of the package directory,
        # not the package directory itself, so a detached development-mode
        # runtime can import ``c4harness`` after changing cwd to the workload.
        package_root = str(Path(__file__).resolve().parents[2])
        runtime_env["PYTHONPATH"] = os.pathsep.join(
            part for part in [package_root, runtime_env.get("PYTHONPATH", "")] if part
        )
        with runtime_log.open("a", encoding="utf-8") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "c4harness.delegator.async_runtime",
                    "--task-id",
                    config.id,
                    "--memory",
                    str(memory_path),
                ],
                cwd=repo,
                env=runtime_env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        store.update(config.id, runtime_pid=process.pid)
        threading.Thread(target=process.wait, daemon=True).start()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            current = store.get(config.id)
            if not current or current["status"] != "pending" or process.poll() is not None:
                break
            time.sleep(0.02)
        payload = _async_task_payload(store, config.id)
        payload["runtime_log"] = str(runtime_log)
        _print_async_payload(payload, args.json)
        return 0
    if args.async_command == "status":
        payload = _async_task_payload(store, args.task_id)
        if not payload:
            print(f"not found: {args.task_id}")
            return 1
        _print_async_payload(payload, args.json)
        return 0
    if args.async_command == "list":
        payload = [_decode_async_record(item) for item in store.list(args.limit)]
        _print_async_payload(payload, args.json)
        return 0
    if args.async_command == "events":
        if not store.get(args.task_id):
            print(f"not found: {args.task_id}")
            return 1
        _print_async_payload(store.events(args.task_id, args.limit), args.json)
        return 0
    if args.async_command == "stop":
        stopped = store.request_stop(args.task_id)
        print("stop requested" if stopped else "task not found or already finished")
        return 0 if stopped else 1
    if args.async_command == "inbox":
        payload = store.inbox(
            limit=args.limit,
            unread_only=args.unread_only,
            source_thread_id=args.thread_id,
        )
        _print_async_payload(payload, args.json)
        return 0
    if args.async_command == "ack":
        acknowledged = store.acknowledge_inbox(args.inbox_id)
        print("acknowledged" if acknowledged else "inbox item not found")
        return 0 if acknowledged else 1
    return 2


def _async_task_payload(store, task_id: str) -> dict | None:
    record = store.get(task_id)
    if not record:
        return None
    payload = _decode_async_record(record)
    payload["events"] = store.events(task_id, 20)
    payload["task_dir"] = str(Path(store.path).parent / "async-tasks" / task_id)
    return payload


def _decode_async_record(record: dict) -> dict:
    payload = dict(record)
    payload["delivery_mode"] = payload.pop("callback_mode", "inbox")
    payload.pop("codex_command", None)
    payload["workload_command"] = json.loads(payload.pop("workload_command_json"))
    payload["log_paths"] = json.loads(payload.pop("log_paths_json"))
    payload["stop_requested"] = bool(payload["stop_requested"])
    return payload


def _print_async_payload(payload, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for item in payload:
            if "event_type" in item and "task_id" in item:
                print(
                    f"{item['id']}  {item['status']:<12}  "
                    f"{item['event_type']}  {item['task_id']}"
                )
            else:
                print(f"{item['id']}  {item['status']:<10}  {item['goal']}")
        return
    if "id" in payload:
        print(f"Async task: {payload['id']}")
        print(f"Status: {payload['status']}")
        print(f"Goal: {payload['goal']}")
        print(f"Task directory: {payload.get('task_dir', '-')}")
        if payload.get("last_worker_summary"):
            print(f"Worker: {payload['last_worker_summary']}")
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def _redact_command(command: list[str], provider) -> list[str]:
    redacted = []
    for part in command:
        if provider is not None:
            part = part.replace(provider.base_url, "<provider-base-url>")
            secret = os.environ.get(provider.api_key_env)
            if secret:
                part = part.replace(secret, "<provider-api-key>")
        redacted.append(part)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
