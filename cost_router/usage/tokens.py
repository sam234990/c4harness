from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from ..core.contracts import Task, TokenAnalysis, TokenUsage, WorkerResult


TOKEN_USED_RE = re.compile(r"tokens used\s*\n\s*([\d,]+)", re.IGNORECASE)


def extract_token_usage(text: str) -> TokenUsage:
    """Best-effort token usage extraction from CLI output.

    Codex CLI currently prints a "tokens used" footer in non-JSON mode.
    Other tools often expose usage in JSON, so we try both paths.
    """
    usage = _extract_from_json(text)
    if usage.total_tokens or usage.input_tokens or usage.output_tokens:
        return usage

    match = TOKEN_USED_RE.search(text)
    if match:
        return TokenUsage(total_tokens=_parse_int(match.group(1)), source="codex_footer")

    return TokenUsage()


def estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return estimate_token_count_from_chars(len(text))


def estimate_token_count_from_chars(char_count: int) -> int:
    if char_count <= 0:
        return 0
    return max(1, math.ceil(char_count / 4))


def estimate_delegation_savings(task: Task, result: WorkerResult | None = None) -> TokenAnalysis:
    delegated_chars = len(task.goal)
    unique_paths = dict.fromkeys([*task.paths, *task.write_paths, *task.context_packs])
    for path in unique_paths:
        delegated_chars += _safe_content_len(path)
    delegated_tokens = estimate_token_count_from_chars(delegated_chars)

    returned_text = ""
    if result:
        returned_text = "\n".join(
            [
                result.summary,
                *[item.observation for item in result.evidence],
                *result.risks,
                *result.next_steps,
            ]
        )
    returned_tokens = estimate_token_count(returned_text) if returned_text else 0

    return TokenAnalysis(
        delegated_context_tokens_estimate=delegated_tokens,
        returned_result_tokens_estimate=returned_tokens,
        estimated_main_tokens_saved=max(0, delegated_tokens - returned_tokens),
    )


def _safe_content_len(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            total = 0
            for child in path.rglob("*"):
                if child.is_file() and not _is_ignored_path(child):
                    total += child.stat().st_size
            return total
    except OSError:
        return len(str(path))
    return len(str(path))


def _is_ignored_path(path: Path) -> bool:
    ignored = {".git", ".cost-router", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return any(part in ignored for part in path.parts)


def _extract_from_json(text: str) -> TokenUsage:
    candidates = [text.strip()]
    candidates.extend(line.strip() for line in text.splitlines() if line.strip().startswith("{"))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        usage = _find_usage(parsed)
        if usage:
            return usage
    return TokenUsage()


def _find_usage(value: Any) -> TokenUsage | None:
    if isinstance(value, dict):
        direct = _usage_from_mapping(value)
        if direct:
            return direct
        for child in value.values():
            found = _find_usage(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_usage(child)
            if found:
                return found
    return None


def _usage_from_mapping(value: dict[str, Any]) -> TokenUsage | None:
    input_tokens = _first_int(
        value,
        "input_tokens",
        "prompt_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    output_tokens = _first_int(value, "output_tokens", "completion_tokens")
    total_tokens = _first_int(value, "total_tokens")

    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        source="json_usage",
    )


def _first_int(value: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        raw = value.get(key)
        parsed = _parse_int(raw)
        if parsed is not None:
            return parsed
    return None


def _parse_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return None
    return None
