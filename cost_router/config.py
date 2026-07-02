from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(slots=True)
class ProviderConfig:
    provider_id: str
    name: str
    base_url: str
    model: str
    api_key_env: str
    wire_api: str = "responses"

    def validate(self) -> None:
        missing = []
        for key, value in {
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
        }.items():
            if not value:
                missing.append(key)
        if missing:
            raise ConfigError(f"Missing provider fields: {', '.join(missing)}")
        if self.wire_api != "responses":
            raise ConfigError("Codex 0.139+ requires wire_api='responses' for custom providers.")
        if not os.environ.get(self.api_key_env):
            raise ConfigError(f"Environment variable {self.api_key_env} is not set.")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise ConfigError(f"Env file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def provider_from_env(
    *,
    provider_id: str,
    name: str,
    base_url_env: str,
    model_env: str,
    api_key_env: str,
) -> ProviderConfig:
    provider = ProviderConfig(
        provider_id=provider_id,
        name=name,
        base_url=os.environ.get(base_url_env, "").rstrip("/"),
        model=os.environ.get(model_env, ""),
        api_key_env=api_key_env,
    )
    provider.validate()
    return provider
