"""Worker-result and root-contract verification."""

from ..core.contracts import FailureCategory, FailureRecord
from .contracts import VerificationContract, VerificationResult
from .service import verify_node, verify_worker_result
from .phases import combine_phase_results, verify_integrated_node, verify_patch_proposal
from .root import CoverageReport, RootVerificationResult, RootVerifier

__all__ = [
    "CoverageReport",
    "FailureCategory",
    "FailureRecord",
    "RootVerificationResult",
    "RootVerifier",
    "VerificationContract",
    "VerificationResult",
    "verify_node",
    "verify_worker_result",
    "combine_phase_results",
    "verify_integrated_node",
    "verify_patch_proposal",
]
