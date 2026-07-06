"""User-global Worker Capability Manifest configuration."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.graph import WorkerArm, WorkerCapabilities


SCHEMA_VERSION = 1
_ALLOWED_TOP = {"version", "revision", "workers"}
_SECRET_NAMES = {"api_key", "token", "secret", "password", "base_url"}
_BACKEND_BY_HARNESS = {
    "claude_code": "claude_cli",
    "codex": "codex_subagent",
    "opencode": "external_cli",
    "aider": "external_cli",
}


def default_workers_path() -> Path:
    configured = os.environ.get("COST_ROUTER_WORKERS")
    if configured:
        return Path(configured).expanduser()
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "cost-router" / "workers.json"


def builtin_workers() -> list[dict[str, Any]]:
    return [
        {
            "id": "claude-cli-sonnet", "backend": "claude_cli",
            "harness": "claude_code", "model": "sonnet", "model_alias": "sonnet",
            "enabled": True,
            "policy_profile": "external-staged", "preference_bias": 0.0,
            "capabilities": {
                "modalities": ["text"], "tools": ["read", "grep", "glob", "patch"],
                "write_isolation": "staged_copy", "network": False,
                "structured_output": True, "context_tokens": 100000,
                "persistent_session": True, "provider_protocol": "harness_native",
                "privacy_zone": "approved_external",
                "soft": {"implementation": 0.8, "debugging": 0.8, "documentation": 0.8, "architecture": 0.8},
            },
        },
        {
            "id": "codex-subagent-default", "backend": "codex_subagent",
            "harness": "codex", "model": "configured", "model_alias": "configured",
            "enabled": True,
            "policy_profile": "read-only", "preference_bias": 0.0,
            "capabilities": {
                "modalities": ["text"], "tools": ["read", "grep", "glob"],
                "write_isolation": "none", "network": False,
                "structured_output": True, "context_tokens": 64000,
                "persistent_session": False, "provider_protocol": "responses",
                "privacy_zone": "configured_provider",
                "soft": {"implementation": 0.6, "debugging": 0.7, "documentation": 0.6, "architecture": 0.6},
            },
        },
    ]


@dataclass(frozen=True, slots=True)
class WorkerManifest:
    arm: WorkerArm
    preference_bias: float = 0.0


class WorkerManifestStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_workers_path()

    def load_document(self) -> dict[str, Any]:
        if not self.path.exists():
            workers = builtin_workers()
            return {"version": SCHEMA_VERSION, "revision": _revision(workers), "workers": workers}
        document = json.loads(self.path.read_text(encoding="utf-8"))
        return validate_document(document)

    def registry(self) -> tuple[dict[str, WorkerArm], dict[str, float]]:
        manifests = [manifest_from_dict(item) for item in self.load_document()["workers"]]
        return (
            {item.arm.id: item.arm for item in manifests},
            {item.arm.id: item.preference_bias for item in manifests},
        )

    def save(self, document: dict[str, Any], *, expected_revision: str) -> dict[str, Any]:
        current = self.load_document()
        if current["revision"] != expected_revision:
            raise ValueError("worker manifest revision conflict")
        validated = validate_document(document)
        validated["revision"] = _revision(validated["workers"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="workers-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(validated, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return validated


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) - _ALLOWED_TOP:
        raise ValueError("worker manifest has unknown top-level fields")
    if document.get("version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("unsupported worker manifest version")
    workers = document.get("workers")
    if not isinstance(workers, list):
        raise ValueError("workers must be a list")
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in workers:
        clean_item = _normalize_worker(item)
        manifest = manifest_from_dict(clean_item)
        if manifest.arm.id in ids:
            raise ValueError(f"duplicate worker id: {manifest.arm.id}")
        ids.add(manifest.arm.id)
        normalized.append(clean_item)
    clean = {"version": SCHEMA_VERSION, "workers": normalized}
    clean["revision"] = _revision(normalized)
    return clean


def manifest_from_dict(item: dict[str, Any]) -> WorkerManifest:
    if not isinstance(item, dict):
        raise ValueError("worker must be an object")
    if any(name.lower() in _SECRET_NAMES for name in _walk_keys(item)):
        raise ValueError("worker manifest must not contain credentials or base URLs")
    required = {"id", "backend", "harness", "model", "model_alias", "enabled", "policy_profile", "preference_bias", "capabilities"}
    if set(item) != required:
        raise ValueError("worker fields do not match schema")
    preference = _unit(item["preference_bias"], "preference_bias", minimum=-1.0)
    caps = item["capabilities"]
    cap_fields = {"modalities", "tools", "write_isolation", "network", "structured_output", "context_tokens", "persistent_session", "provider_protocol", "privacy_zone", "soft"}
    if not isinstance(caps, dict) or set(caps) != cap_fields:
        raise ValueError("capability fields do not match schema")
    _require_bool(item["enabled"], "enabled")
    for name in ("network", "structured_output", "persistent_session"):
        _require_bool(caps[name], f"capabilities.{name}")
    for name in ("modalities", "tools"):
        if not isinstance(caps[name], list) or not all(
            isinstance(value, str) and value.strip() for value in caps[name]
        ):
            raise ValueError(f"capabilities.{name} must be a list of non-empty strings")
    if not isinstance(caps["soft"], dict):
        raise ValueError("capabilities.soft must be an object")
    soft = {str(name): _unit(value, f"soft.{name}") for name, value in caps["soft"].items()}
    arm = WorkerArm(
        id=_text(item["id"], "id"), backend=_text(item["backend"], "backend"),
        harness=_text(item["harness"], "harness"), model=_text(item["model"], "model"),
        model_alias=_text(item["model_alias"], "model_alias"),
        policy_profile=_text(item["policy_profile"], "policy_profile"), enabled=item["enabled"],
        capabilities=WorkerCapabilities(
            modalities=frozenset(map(str, caps["modalities"])), tools=frozenset(map(str, caps["tools"])),
            write_isolation=str(caps["write_isolation"]), network=caps["network"],
            structured_output=caps["structured_output"], context_tokens=int(caps["context_tokens"]),
            persistent_session=caps["persistent_session"], provider_protocol=str(caps["provider_protocol"]),
            privacy_zone=str(caps["privacy_zone"]), soft=soft,
        ),
    )
    if arm.capabilities.context_tokens < 0:
        raise ValueError("context_tokens must be non-negative")
    return WorkerManifest(arm, preference)


def _normalize_worker(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("worker must be an object")
    normalized = dict(item)
    normalized.setdefault("model_alias", normalized.get("model"))
    harness = normalized.get("harness")
    if harness in _BACKEND_BY_HARNESS:
        normalized["backend"] = _BACKEND_BY_HARNESS[harness]
    return normalized


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _text(value: Any, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} cannot be empty")
    return text


def _unit(value: Any, name: str, *, minimum: float = 0.0) -> float:
    number = float(value)
    if not minimum <= number <= 1.0:
        raise ValueError(f"{name} must be between {minimum} and 1")
    return number


def _require_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _revision(workers: list[dict[str, Any]]) -> str:
    payload = json.dumps(workers, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]
