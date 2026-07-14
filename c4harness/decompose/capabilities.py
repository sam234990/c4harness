from __future__ import annotations

from dataclasses import dataclass, field

from ..core.graph import HardCapabilityRequirements, WorkerArm


@dataclass(frozen=True, slots=True)
class CapabilityMatch:
    eligible: bool
    reasons: tuple[str, ...] = ()


def match_capabilities(
    requirements: HardCapabilityRequirements,
    worker: WorkerArm,
) -> CapabilityMatch:
    if not worker.enabled:
        return CapabilityMatch(False, ("worker is disabled",))

    capabilities = worker.capabilities
    reasons: list[str] = []
    if not requirements.modalities.issubset(capabilities.modalities):
        missing = requirements.modalities - capabilities.modalities
        reasons.append("missing modalities: " + ", ".join(sorted(missing)))
    if not requirements.tools.issubset(capabilities.tools):
        missing = requirements.tools - capabilities.tools
        reasons.append("missing tools: " + ", ".join(sorted(missing)))
    if (
        requirements.write_isolation
        and capabilities.write_isolation not in requirements.write_isolation
    ):
        reasons.append(
            "unsupported write isolation: " + capabilities.write_isolation
        )
    if requirements.network_required and not capabilities.network:
        reasons.append("network access is required")
    if requirements.structured_output_required and not capabilities.structured_output:
        reasons.append("structured output is required")
    if capabilities.context_tokens < requirements.min_context_tokens:
        reasons.append(
            f"context limit {capabilities.context_tokens} < {requirements.min_context_tokens}"
        )
    if requirements.persistent_session_required and not capabilities.persistent_session:
        reasons.append("persistent session is required")
    if (
        requirements.provider_protocols
        and capabilities.provider_protocol not in requirements.provider_protocols
    ):
        reasons.append("unsupported provider protocol: " + capabilities.provider_protocol)
    if requirements.privacy_zones and capabilities.privacy_zone not in requirements.privacy_zones:
        reasons.append("privacy zone is not allowed: " + capabilities.privacy_zone)
    return CapabilityMatch(not reasons, tuple(reasons))


@dataclass(slots=True)
class WorkerRegistry:
    workers: dict[str, WorkerArm] = field(default_factory=dict)

    def register(self, worker: WorkerArm) -> None:
        if worker.id in self.workers:
            raise ValueError(f"Duplicate worker id: {worker.id}")
        self.workers[worker.id] = worker

    def get(self, worker_id: str) -> WorkerArm:
        try:
            return self.workers[worker_id]
        except KeyError as error:
            raise KeyError(f"Unknown worker id: {worker_id}") from error

    def evaluate(
        self, requirements: HardCapabilityRequirements
    ) -> dict[str, CapabilityMatch]:
        return {
            worker_id: match_capabilities(requirements, worker)
            for worker_id, worker in self.workers.items()
        }

    def eligible(self, requirements: HardCapabilityRequirements) -> list[WorkerArm]:
        matches = self.evaluate(requirements)
        return [
            worker
            for worker_id, worker in self.workers.items()
            if matches[worker_id].eligible
        ]
