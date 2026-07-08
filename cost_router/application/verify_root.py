"""Application facade for final task-contract verification.

``verify_root`` is the Phase-3 use case that:

1. Builds a :class:`RootVerifier` and invokes :meth:`RootVerifier.verify`.
2. Fires the ``post_root_verify`` lifecycle hook.
3. Returns an inspectable :class:`RootVerificationResult`.

This facade does **not** select workers, write shared memory, or invoke any
backend.  It composes the root verifier with the hook dispatcher so the
caller (CLI, dashboard, or orchestrator loop) can inspect the outcome and
decide next steps.

Design decisions
================
* **No shared-memory writes** -- the result is returned to the caller who
  decides whether and how to persist it.
* **Hook compatibility** -- ``post_root_verify`` receives a plain
  :class:`VerificationResult` (the existing contract) so hooks do not need
  to know about the extended ``RootVerificationResult``.
* **Explicit decisions** -- semantic criteria require the caller to supply
  ``explicit_decisions``; the facade forwards them unchanged.
"""

from __future__ import annotations

from ..core.contracts import Evidence, VerificationResult
from ..core.graph import DecompositionPlan
from ..delegator.scheduler import GraphResult
from ..hooks import HookSet
from ..verifier.root import RootVerificationResult, RootVerifier


def verify_root(
    plan: DecompositionPlan,
    graph_result: GraphResult,
    node_verifications: dict[str, VerificationResult],
    node_evidence: dict[str, list[Evidence]] | None = None,
    explicit_decisions: dict[str, bool] | None = None,
    hooks: HookSet | None = None,
) -> RootVerificationResult:
    """Application facade for root verification.

    Invokes the deterministic root verifier and fires the
    ``post_root_verify`` hook.  Does not select workers or write shared
    memory.

    Parameters
    ----------
    plan:
        The compiled decomposition plan (situation, root contract, graph).
    graph_result:
        Inspectable result of graph execution with per-node terminal states.
    node_verifications:
        Per-node verification outcomes keyed by ``node_id``.
    node_evidence:
        Optional per-node evidence references for artifact-conflict
        detection.
    explicit_decisions:
        Optional orchestrator/reviewer decisions for semantic criteria
        (``criterion_id -> bool``).
    hooks:
        Optional :class:`HookSet` whose ``post_root_verify`` will be called
        with a plain :class:`VerificationResult` for backward compatibility.

    Returns
    -------
    RootVerificationResult
        Acceptance/rejection/inconclusive outcome with serializable coverage
        report.
    """
    verifier = RootVerifier()
    result = verifier.verify(
        plan=plan,
        graph_result=graph_result,
        node_verifications=node_verifications,
        node_evidence=node_evidence,
        explicit_decisions=explicit_decisions,
    )

    if hooks is not None:
        hook_vr = VerificationResult(
            accepted=result.accepted,
            confidence=result.confidence,
            issues=list(result.issues),
            memory_facts=list(result.memory_facts),
        )
        hooks.post_root_verify(plan, hook_vr)

    return result
