from __future__ import annotations

import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ...config.providers import ProviderConfig
from ...core.contracts import Evidence, Task, WorkerResult
from ...usage import estimate_delegation_savings, extract_token_usage


@dataclass(slots=True)
class CodexSubagentBackend:
    provider: ProviderConfig
    worker_name: str = "cheap_explorer"
    work_dir: Path = Path(".c4harness")

    def prepare(self, task: Task) -> tuple[Path, Path, list[str], str]:
        run_dir = self.work_dir / "runs" / f"{task.id}_{uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        agent_file = run_dir / f"{self.worker_name}.toml"
        output_file = run_dir / "codex-output.md"
        agent_file.write_text(self._agent_toml(), encoding="utf-8")
        prompt = self._prompt(task)
        return agent_file, output_file, self._command(task, agent_file, output_file, prompt), prompt

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
        stdout_file = run_dir / "codex-stdout.txt"
        stderr_file = run_dir / "codex-stderr.txt"
        env = os.environ.copy()
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            check=False,
        )
        stdout_file.write_text(completed.stdout, encoding="utf-8")
        stderr_file.write_text(completed.stderr, encoding="utf-8")
        raw_output = output_file.read_text(encoding="utf-8") if output_file.exists() else completed.stdout
        token_usage = extract_token_usage("\n".join([completed.stdout, completed.stderr, raw_output]))
        if completed.returncode != 0:
            raw_output = "\n".join(
                part for part in [raw_output, completed.stderr.strip()] if part
            )
            failed = WorkerResult(
                status="failed",
                summary=f"codex exec failed with exit code {completed.returncode}",
                risks=[_truncate(raw_output, 2000)],
                raw_output_path=output_file if output_file.exists() else stderr_file,
                token_usage=token_usage,
            )
            failed.token_analysis = estimate_delegation_savings(task, failed)
            return failed

        result = parse_codex_output(raw_output, output_file, token_usage=token_usage)
        result.token_analysis = estimate_delegation_savings(task, result)
        return result

    def run(self, task: Task, timeout_sec: int) -> WorkerResult:
        _, output_file, command, _ = self.prepare(task)
        return self.run_prepared(
            task=task,
            command=command,
            output_file=output_file,
            timeout_sec=timeout_sec,
            cwd=task.repo,
        )

    def _agent_toml(self) -> str:
        return textwrap.dedent(
            f"""
            name = "{self.worker_name}"
            description = "Read-only low-cost exploration agent for logs and code search."
            model = "{self.provider.model}"
            model_provider = "{self.provider.provider_id}"
            model_reasoning_effort = "low"
            sandbox_mode = "read-only"

            developer_instructions = \"\"\"
            You are a read-only exploration agent.
            Do not edit files.
            Use concise evidence with file paths.
            Return structured Markdown with sections: Summary, Evidence, Risks, Next Steps.
            Keep output under 12 bullets total.
            \"\"\"
            """
        ).strip() + "\n"

    def _prompt(self, task: Task) -> str:
        paths = "\n".join(f"- {path}" for path in task.paths) or "- <none>"
        context_packs = "\n".join(f"- {path}" for path in task.context_packs) or "- <none>"
        return textwrap.dedent(
            f"""
            Spawn the {self.worker_name} subagent to complete this read-only task.
            Wait for the subagent result, then return only a concise structured summary.

            Goal:
            {task.goal}

            Paths:
            {paths}

            Context Packs:
            {context_packs}

            Required final format:
            ## Summary
            ## Evidence
            ## Risks
            ## Next Steps

            Do not edit files.
            """
        ).strip()

    def _command(
        self,
        task: Task,
        agent_file: Path,
        output_file: Path,
        prompt: str,
    ) -> list[str]:
        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "-c",
            'model_provider="openai"',
            "-c",
            f'model_providers.{self.provider.provider_id}.name="{self.provider.name}"',
            "-c",
            f'model_providers.{self.provider.provider_id}.base_url="{self.provider.base_url}"',
            "-c",
            f'model_providers.{self.provider.provider_id}.wire_api="{self.provider.wire_api}"',
            "-c",
            f'model_providers.{self.provider.provider_id}.env_key="{self.provider.api_key_env}"',
            "-c",
            "agents.max_threads=2",
            "-c",
            f'agents.{self.worker_name}.description="Read-only low-cost exploration agent"',
            "-c",
            f'agents.{self.worker_name}.config_file="{agent_file.resolve()}"',
            "-o",
            str(output_file.resolve()),
        ]
        for path in [*task.paths, *task.context_packs]:
            if path.exists():
                add_dir = path if path.is_dir() else path.parent
                cmd.extend(["--add-dir", str(add_dir.resolve())])
        cmd.append(prompt)
        return cmd


def parse_codex_output(raw_output: str, output_file: Path | None = None, token_usage=None) -> WorkerResult:
    sections = _parse_sections(raw_output)
    evidence_items = []
    evidence_path = str(output_file) if output_file else "<codex-output>"
    for line in sections.get("evidence", []):
        stripped = line.lstrip("- ").strip()
        if stripped:
            evidence_items.append(Evidence(path=evidence_path, observation=stripped))

    return WorkerResult(
        status="success",
        summary="\n".join(sections.get("summary", [])).strip() or raw_output.strip(),
        evidence=evidence_items,
        risks=[line.lstrip("- ").strip() for line in sections.get("risks", []) if line.strip()],
        next_steps=[
            line.lstrip("- ").strip() for line in sections.get("next steps", []) if line.strip()
        ],
        raw_output_path=output_file,
        token_usage=token_usage or extract_token_usage(raw_output),
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


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 20] + "\n<truncated>"
