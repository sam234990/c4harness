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
    parser = argparse.ArgumentParser(prog="cost-router")
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
    async_start.add_argument("--codex-command", default="codex")
    async_start.add_argument(
        "--callback",
        choices=["auto", "codex-resume", "none"],
        default="auto",
        help="How significant worker and terminal events return to the orchestrator",
    )
    async_start.add_argument(
        "--thread-id", default=None, help="Codex thread to resume; defaults to CODEX_THREAD_ID"
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

    async_retry = async_subparsers.add_parser(
        "retry-callbacks", help="Retry queued or failed Codex callbacks"
    )
    async_retry.add_argument("task_id", nargs="?")
    async_retry.add_argument("--memory", default=str(default_memory_path()))
    async_retry.add_argument("--json", action="store_true")

    return parser


def run_command(args: argparse.Namespace) -> int:
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
        decide = lambda current: make_claude_decision(args, current)
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


def make_claude_decision(args: argparse.Namespace, task: Task):
    from ..core.contracts import Difficulty, Risk, RouteDecision

    return RouteDecision(
        difficulty=Difficulty.MEDIUM if task.constraints.mode == TaskMode.PATCH else Difficulty.SIMPLE,
        risk=Risk.PATCH if task.constraints.mode == TaskMode.PATCH else Risk.READ_ONLY,
        can_delegate=True,
        backend="claude_cli",
        worker="claude_cli",
        model=args.claude_model or "claude-default",
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
    print("Cost Router")
    print("===========")
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
        print("Cost Router Memory")
        print("==================")
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
        print("Cost Router user setup")
        print("======================")
        print(f"Global ledger: {payload['memory_path']}")
        print(f"User skill: {payload['skill_path']} ({payload['skill_status']})")
        print("\nAdd this to ~/.codex/config.toml, then restart Codex:")
        print(payload["codex_config"])
        print("\nLaunch the console with: cost-router dashboard")
    return 0


def async_task_command(args: argparse.Namespace) -> int:
    from ..delegator.async_runtime import AsyncTaskConfig, AsyncTaskRuntime, AsyncTaskStore, retry_callbacks

    if not args.async_command:
        print("usage: cost-router async-task {start,status,list,events,stop,retry-callbacks}")
        return 2
    memory_path = Path(args.memory).expanduser().resolve()
    store = AsyncTaskStore(memory_path)
    if args.async_command == "start":
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
        callback_mode = args.callback
        if callback_mode == "auto":
            callback_mode = "codex-resume" if thread_id else "none"
        if callback_mode == "codex-resume" and not thread_id:
            print("config error: codex-resume callback requires --thread-id or CODEX_THREAD_ID")
            return 2
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
            callback_mode="codex_resume" if callback_mode == "codex-resume" else "none",
            claude_command=args.claude_command,
            codex_command=args.codex_command,
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
        package_root = str(Path(__file__).resolve().parents[1])
        runtime_env["PYTHONPATH"] = os.pathsep.join(
            part for part in [package_root, runtime_env.get("PYTHONPATH", "")] if part
        )
        with runtime_log.open("a", encoding="utf-8") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "cost_router.delegator.async_runtime",
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
    if args.async_command == "retry-callbacks":
        attempted, delivered = retry_callbacks(memory_path, args.task_id)
        payload = {"attempted": attempted, "delivered": delivered}
        _print_async_payload(payload, args.json)
        return 0 if attempted == delivered else 1
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
