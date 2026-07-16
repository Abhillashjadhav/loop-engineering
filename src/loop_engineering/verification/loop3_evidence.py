"""Loop 3 — Independent Evidence Verification (spec §6).

Evidence rules:
- normal material claim: at least two independent evidence origins;
- high-impact claim: at least three independent evidence origins;
- a README statement is not independent corroboration on its own;
- absence claims require explicit search coverage;
- uncertainty and source conflict stay visible;
- unsupported claims are excluded from final percentages, never averaged in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from loop_engineering.domain.models import (
    CheckResult,
    Claim,
    ClaimImpact,
    ClaimKind,
    VerificationResult,
    utc_now,
)

VERIFIER_ROLE = "evidence-verifier"

#: Origins that only restate the author's own description of the work.
SELF_DESCRIBED_ORIGINS = frozenset({"readme", "self_description", "marketing_page"})

NORMAL_MIN_SOURCES = 2
HIGH_IMPACT_MIN_SOURCES = 3


def independent_origins(claim: Claim) -> set[str]:
    """Distinct evidence origins; multiple items from one origin count once."""
    return {e.origin for e in claim.evidence}


def is_supported(claim: Claim) -> tuple[bool, str]:
    """Apply the independence rules to one claim. Returns (supported, reason)."""
    origins = independent_origins(claim)
    required = HIGH_IMPACT_MIN_SOURCES if claim.impact == ClaimImpact.HIGH else NORMAL_MIN_SOURCES
    non_self = origins - SELF_DESCRIBED_ORIGINS
    if not non_self:
        return False, (
            "only self-described sources (e.g. README) back this claim; "
            "a README statement is not independent corroboration"
        )
    if len(origins) < required:
        return False, (
            f"{len(origins)} independent origin(s) found, {required} required "
            f"for {claim.impact.value} impact"
        )
    if claim.kind == ClaimKind.ABSENCE:
        if claim.search_coverage is None or not claim.search_coverage.queries:
            return False, "absence claim without an explicit search-coverage record"
        if not claim.search_coverage.complete:
            return False, "absence claim whose search coverage is recorded as incomplete"
    return True, "meets independence rules"


@dataclass
class EvidenceCoverage:
    total_claims: int
    supported_claims: int
    unsupported_claim_ids: list[str]
    conflicted_claim_ids: list[str]

    @property
    def supported_pct(self) -> float:
        if self.total_claims == 0:
            return 0.0
        return round(self.supported_claims / self.total_claims * 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "supported_pct": self.supported_pct,
            "unsupported_claim_ids": list(self.unsupported_claim_ids),
            "conflicted_claim_ids": list(self.conflicted_claim_ids),
        }


def verify_claims(claims: list[Claim]) -> tuple[list[VerificationResult], EvidenceCoverage]:
    """Verify every material claim; return per-claim results and coverage stats.

    Unsupported claims are surfaced (never silently dropped) and excluded from
    any percentage computed downstream.
    """
    results: list[VerificationResult] = []
    unsupported: list[str] = []
    conflicted: list[str] = []
    for claim in claims:
        supported, reason = is_supported(claim)
        checks = [
            CheckResult("independence_rules", supported, reason),
            CheckResult(
                "conflicts_visible",
                True,
                f"{len(claim.conflicts)} recorded conflict(s)" if claim.conflicts else "none",
            ),
        ]
        if claim.conflicts:
            conflicted.append(claim.claim_id)
        if not supported:
            unsupported.append(claim.claim_id)
        results.append(
            VerificationResult(
                verification_id=f"v3-{claim.claim_id}-{uuid.uuid4().hex[:8]}",
                loop="loop3_evidence",
                subject_id=claim.claim_id,
                verifier_role=VERIFIER_ROLE,
                passed=supported,
                checks=checks,
                failure_reason=None if supported else reason,
                verified_at=utc_now(),
            )
        )
    cov = EvidenceCoverage(
        total_claims=len(claims),
        supported_claims=len(claims) - len(unsupported),
        unsupported_claim_ids=unsupported,
        conflicted_claim_ids=conflicted,
    )
    return results, cov
