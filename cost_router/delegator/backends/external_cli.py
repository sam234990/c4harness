from __future__ import annotations

import os
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from ...core.contracts import Evidence, Task, TaskMode, WorkerResult
from ...usage import estimate_delegation_savings, extract_token_usage


@dataclass(slots=True)
class ExternalCliBackend:
    command: str
    name: str = "external_cli"
    model: str | None = None
    base_args: list[str] = field(default_factory=list)
    read_only_tools: str | None = None
    patch_tools: str | None = None
    work_dir: Path = Path(".cost-router")

    def prepare(self, task: Task) -> tuple[Path, list[str], str]:
        run_dir = self.work_dir / "runs" / f"{task.id}_{uuid4().hex[:8]}_{self.name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        output_file = run_dir / f"{self.name}-output.md"
        workspace = run_dir / "workspace"
        staged_inputs = _stage_task_inputs(task, workspace, run_dir)
        prompt = self._prompt(task, staged_inputs)
        return output_file, self._command(task, prompt), prompt

    def run_prepared(
        self,
        *,
        task: Task,
        command: list[str],
        output_file: Path,
        timeout_sec: int,
        cwd: Path,
    ) -> WorkerResult:
        run_dir = output_file.parent
        stdout_file = run_dir / f"{self.name}-stdout.txt"
        stderr_file = run_dir / f"{self.name}-stderr.txt"
        workspace = run_dir / "workspace"
        completed = subprocess.run(
            command,
            cwd=workspace if workspace.exists() else cwd,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            check=False,
        )
        stdout_file.write_text(completed.stdout, encoding="utf-8")
        stderr_file.write_text(completed.stderr, encoding="utf-8")
        raw_stdout = completed.stdout.strip()
        token_usage = extract_token_usage("\n".join([completed.stdout, completed.stderr]))
        raw_output = _extract_result_text(raw_stdout)
        output_file.write_text(raw_output, encoding="utf-8")

        if completed.returncode != 0:
            failed = WorkerResult(
                status="failed",
                summary=f"{self.name} failed with exit code {completed.returncode}",
                risks=[_truncate(completed.stderr.strip() or completed.stdout.strip(), 2000)],
                raw_output_path=stderr_file,
                token_usage=token_usage,
            )
            failed.token_analysis = estimate_delegation_savings(task, failed)
            return failed

        result = parse_external_cli_output(raw_output, output_file, token_usage=token_usage)
        if task.constraints.mode == TaskMode.PATCH:
            proposal = _collect_patch_proposal(task, workspace, run_dir)
            result.proposed_patch_path = proposal.path
            result.changed_paths = proposal.changed_paths
            result.policy_violations = proposal.policy_violations
        result.token_analysis = estimate_delegation_savings(task, result)
        return result

    def _command(self, task: Task, prompt: str) -> list[str]:
        cmd = [self.command, *self.base_args]
        permission_mode = "acceptEdits" if task.constraints.mode == TaskMode.PATCH else "dontAsk"
        cmd.extend(["--permission-mode", permission_mode])
        tools = self.patch_tools if task.constraints.mode == TaskMode.PATCH else self.read_only_tools
        if tools:
            cmd.extend(["--tools", tools])
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(["--", prompt])
        return cmd

    def _prompt(self, task: Task, staged_inputs: list["StagedInput"] | None = None) -> str:
        paths = _format_staged_inputs(staged_inputs or [], "path")
        write_paths = _format_staged_inputs(staged_inputs or [], "write_path")
        context_packs = _format_staged_inputs(staged_inputs or [], "context_pack")
        if task.constraints.mode == TaskMode.PATCH:
            instruction = "\n".join(
                [
                    "Complete this coding task by editing only the staged writable paths listed below.",
                    "Read-only paths and context packs must not be modified.",
                    "Do not create or modify any other files, including MANIFEST.md.",
                    "The real repository is not mounted here; your changes will be returned as a patch proposal.",
                ]
            )
        else:
            instruction = "Complete this read-only coding task.\nDo not edit or create files."
        return (
            f"{instruction}\n"
            "You are running in a staged workspace that contains only delegated files.\n"
            "Use only the staged relative paths below for file access.\n"
            "The orchestrator recorded this transfer as "
            f"external_policy={task.constraints.external_policy.value}, "
            f"data_classification={task.constraints.data_classification.value}.\n"
            "Return structured Markdown with sections: Summary, Evidence, Risks, Next Steps.\n\n"
            f"Goal:\n{task.goal}\n\n"
            f"Staged Paths:\n{paths}\n\n"
            f"Staged Writable Paths:\n{write_paths}\n\n"
            f"Staged Context Packs:\n{context_packs}"
        )


def claude_cli_backend(
    command: str = "claude",
    model: str | None = None,
    work_dir: Path = Path(".cost-router"),
) -> ExternalCliBackend:
    return ExternalCliBackend(
        command=command,
        name="claude_cli",
        model=model,
        base_args=[
            "-p",
            "--output-format",
            "json",
            "--safe-mode",
            "--no-session-persistence",
            "--strict-mcp-config",
        ],
        read_only_tools="Read,Grep,Glob",
        patch_tools="Read,Grep,Glob,Edit,Write",
        work_dir=work_dir,
    )


@dataclass(frozen=True, slots=True)
class StagedInput:
    kind: str
    original: Path
    staged: Path | None
    status: str


@dataclass(frozen=True, slots=True)
class PatchProposal:
    path: Path | None
    changed_paths: list[str]
    policy_violations: list[str]


def _stage_task_inputs(task: Task, workspace: Path, run_dir: Path) -> list[StagedInput]:
    workspace.mkdir(parents=True, exist_ok=True)
    staged: list[StagedInput] = []
    writable = {path.resolve() for path in task.write_paths}
    groups = (
        ("path", [path for path in task.paths if path.resolve() not in writable]),
        ("write_path", task.write_paths),
        ("context_pack", task.context_packs),
    )
    for kind, paths in groups:
        for index, original in enumerate(paths, start=1):
            target = workspace / kind / f"{index:03d}_{_safe_stage_name(original)}"
            if not original.exists():
                if kind == "write_path":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    staged.append(
                        StagedInput(
                            kind=kind,
                            original=original,
                            staged=target.relative_to(workspace),
                            status="new",
                        )
                    )
                else:
                    staged.append(
                        StagedInput(kind=kind, original=original, staged=None, status="missing")
                    )
                continue
            _copy_readable_path(original, target)
            staged.append(
                StagedInput(
                    kind=kind,
                    original=original,
                    staged=target.relative_to(workspace),
                    status="staged",
                )
            )
    manifest = workspace / "MANIFEST.md"
    manifest.write_text(_staged_manifest(staged), encoding="utf-8")
    _write_internal_manifest(run_dir / "staging.json", staged)
    shutil.copytree(workspace, run_dir / "baseline_workspace")
    return staged


def _copy_readable_path(source: Path, target: Path) -> None:
    resolved = source.resolve()
    if resolved.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, target)
        return
    if resolved.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in resolved.rglob("*"):
            if _is_ignored_staged_path(child) or child.is_symlink():
                continue
            relative = child.relative_to(resolved)
            destination = target / relative
            if child.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif child.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, destination)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"Unsupported delegated path type: {source}\n", encoding="utf-8")


def _is_ignored_staged_path(path: Path) -> bool:
    ignored = {".git", ".cost-router", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return any(part in ignored for part in path.parts)


def _safe_stage_name(path: Path) -> str:
    name = path.name or "input"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return safe or "input"


def _format_staged_inputs(staged_inputs: list[StagedInput], kind: str) -> str:
    lines = []
    for item in staged_inputs:
        if item.kind != kind:
            continue
        if item.staged is None:
            lines.append("- <missing>")
        else:
            suffix = " (new file)" if item.status == "new" else ""
            lines.append(f"- {item.staged}{suffix}")
    return "\n".join(lines) or "- <none>"


def _staged_manifest(staged_inputs: list[StagedInput]) -> str:
    lines = [
        "# Staged Claude CLI Inputs",
        "",
        "This workspace contains copies of the files delegated to the Claude CLI worker.",
        "Use only staged paths for file access.",
        "",
    ]
    for item in staged_inputs:
        staged = str(item.staged) if item.staged else "<missing>"
        lines.append(f"- kind={item.kind} staged={staged} status={item.status}")
    return "\n".join(lines) + "\n"


def _write_internal_manifest(path: Path, staged_inputs: list[StagedInput]) -> None:
    payload = [
        {
            "kind": item.kind,
            "original": str(item.original),
            "staged": str(item.staged) if item.staged else None,
            "status": item.status,
        }
        for item in staged_inputs
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _collect_patch_proposal(task: Task, workspace: Path, run_dir: Path) -> PatchProposal:
    baseline = run_dir / "baseline_workspace"
    before = _workspace_hashes(baseline)
    after = _workspace_hashes(workspace)
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    staged = json.loads((run_dir / "staging.json").read_text(encoding="utf-8"))
    writable = [item for item in staged if item["kind"] == "write_path" and item["staged"]]
    violations: list[str] = []
    patch_parts: list[str] = []
    changed_labels: list[str] = []

    for relative in changed:
        mapping = _writable_mapping(relative, writable)
        if mapping is None:
            violations.append(f"Worker modified path outside write allowlist: {relative}")
            continue
        original = _mapped_original_path(relative, mapping)
        label = _repo_relative_label(task.repo, original)
        changed_labels.append(label)
        old_text = _read_patch_text(baseline / relative)
        new_text = _read_patch_text(workspace / relative)
        if old_text is None or new_text is None:
            violations.append(f"Binary or unreadable change cannot be proposed: {label}")
            continue
        diff = _unified_patch(label, old_text, new_text, (baseline / relative).exists(), (workspace / relative).exists())
        if diff:
            patch_parts.append(diff)

    patch_path = run_dir / "proposed.patch"
    if patch_parts:
        patch_path.write_text("\n".join(patch_parts), encoding="utf-8")
        proposal_path: Path | None = patch_path
    else:
        proposal_path = None
    return PatchProposal(proposal_path, changed_labels, violations)


def _workspace_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not root.exists():
        return hashes
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(root).as_posix()
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _writable_mapping(relative: str, writable: list[dict]) -> dict | None:
    candidates = []
    for item in writable:
        root = item["staged"]
        if relative == root or relative.startswith(f"{root}/"):
            candidates.append(item)
    return max(candidates, key=lambda item: len(item["staged"]), default=None)


def _mapped_original_path(relative: str, mapping: dict) -> Path:
    staged_root = mapping["staged"]
    suffix = relative[len(staged_root) :].lstrip("/")
    original = Path(mapping["original"])
    return original / suffix if suffix else original


def _repo_relative_label(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.name


def _read_patch_text(path: Path) -> str | None:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _unified_patch(label: str, old: str, new: str, existed_before: bool, exists_after: bool) -> str:
    if old == new:
        return ""
    fromfile = f"a/{label}" if existed_before else "/dev/null"
    tofile = f"b/{label}" if exists_after else "/dev/null"
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
    )
    return "".join(lines)


def parse_external_cli_output(raw_output: str, output_file: Path | None = None, token_usage=None) -> WorkerResult:
    original_output = raw_output
    result_text = _extract_result_text(raw_output)
    sections = _parse_sections(result_text)
    evidence_path = str(output_file) if output_file else "<external-output>"
    evidence = [
        Evidence(path=evidence_path, observation=line.lstrip("- ").strip())
        for line in sections.get("evidence", [])
        if line.strip()
    ]
    return WorkerResult(
        status="success",
        summary="\n".join(sections.get("summary", [])).strip() or result_text.strip(),
        evidence=evidence,
        risks=[line.lstrip("- ").strip() for line in sections.get("risks", []) if line.strip()],
        next_steps=[
            line.lstrip("- ").strip() for line in sections.get("next steps", []) if line.strip()
        ],
        raw_output_path=output_file,
        token_usage=token_usage or extract_token_usage(original_output),
    )


def _parse_sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        section = _canonical_section(heading.group(2)) if heading else None
        if section:
            current = section
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def _canonical_section(value: str) -> str | None:
    normalized = value.strip().lower().rstrip(":")
    aliases = {
        "summary": "summary",
        "evidence": "evidence",
        "risks": "risks",
        "risk": "risks",
        "next steps": "next steps",
        "next step": "next steps",
        "recommendations": "next steps",
    }
    return aliases.get(normalized)


def _extract_result_text(raw_output: str) -> str:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return raw_output
    if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
        return parsed["result"].strip()
    return raw_output


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 20] + "\n<truncated>"
