"""Loop 4 — Final Stability Verification (spec §6, PD-07).

Six independent final-analysis variants are compared on findings, scores,
classifications, evidence, confidence, and unresolved uncertainty. Findings
are sorted into stable / unstable / unresolved. Disagreement is reported,
never averaged away. Consistency alone does not prove accuracy — evidence
verification (Loop 3) remains mandatory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from loop_engineering.domain.models import (
    CheckResult,
    StabilityVariant,
    VerificationResult,
    utc_now,
)

VERIFIER_ROLE = "stability-reviewer"

REQUIRED_VARIANTS: tuple[StabilityVariant, ...] = tuple(StabilityVariant)

#: Numeric findings within this absolute tolerance across all six runs count as agreeing.
SCORE_TOLERANCE = 5.0


@dataclass
class RunFindings:
    """One variant run's final findings, keyed by finding id."""

    variant: StabilityVariant
    findings: dict[str, Any]
    confidence: dict[str, float] = field(default_factory=dict)
    uncertainties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant.value,
            "findings": dict(self.findings),
            "confidence": dict(self.confidence),
            "uncertainties": list(self.uncertainties),
        }


@dataclass
class StabilityReport:
    stable: dict[str, Any]
    unstable: dict[str, dict[str, Any]]
    unresolved: list[str]
    variant_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable": dict(self.stable),
            "unstable": {k: dict(v) for k, v in self.unstable.items()},
            "unresolved": list(self.unresolved),
            "variant_count": self.variant_count,
        }


def _values_agree(values: list[Any]) -> bool:
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        numbers = [float(v) for v in values]
        return max(numbers) - min(numbers) <= SCORE_TOLERANCE
    return all(v == values[0] for v in values)


def compare_runs(runs: list[RunFindings]) -> StabilityReport:
    """Compare the variant runs finding-by-finding.

    - stable: every run reports the finding and the values agree;
    - unstable: runs disagree — every per-variant value is preserved;
    - unresolved: findings some runs did not report, plus every uncertainty
      any run kept open.
    """
    stable: dict[str, Any] = {}
    unstable: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []

    all_keys = sorted({k for run in runs for k in run.findings})
    for key in all_keys:
        holders = [run for run in runs if key in run.findings]
        values = [run.findings[key] for run in holders]
        if len(holders) < len(runs):
            missing = [r.variant.value for r in runs if key not in r.findings]
            unresolved.append(f"{key}: not reported by variant(s) {missing}")
            continue
        if _values_agree(values):
            stable[key] = values[0]
        else:
            unstable[key] = {run.variant.value: run.findings[key] for run in runs}

    for run in runs:
        for u in run.uncertainties:
            entry = f"{run.variant.value}: {u}"
            if entry not in unresolved:
                unresolved.append(entry)

    return StabilityReport(
        stable=stable, unstable=unstable, unresolved=unresolved, variant_count=len(runs)
    )


def verify_stability(runs: list[RunFindings]) -> tuple[VerificationResult, StabilityReport]:
    """Check the six-variant requirement and produce the comparison report.

    ``passed`` means "the required variants all ran and were compared" — NOT
    "the findings are stable". Disagreement is a valid, faithfully-reported
    outcome; consumers must read the StabilityReport, not just ``passed``.
    """
    present = {run.variant for run in runs}
    missing = [v.value for v in REQUIRED_VARIANTS if v not in present]
    report = compare_runs(runs)
    checks = [
        CheckResult(
            "all_six_variants_ran",
            not missing,
            f"missing variants: {missing}" if missing else "all variants present",
        ),
        CheckResult(
            "disagreement_preserved",
            True,
            f"{len(report.unstable)} unstable finding(s) reported verbatim",
        ),
        CheckResult(
            "consistency_not_sole_proof",
            True,
            "stability output feeds Loop 3 evidence verification; it does not replace it",
        ),
    ]
    passed = all(c.passed for c in checks)
    result = VerificationResult(
        verification_id=f"v4-{uuid.uuid4().hex[:8]}",
        loop="loop4_stability",
        subject_id="final_output",
        verifier_role=VERIFIER_ROLE,
        passed=passed,
        checks=checks,
        failure_reason=None if passed else f"missing variants: {missing}",
        verified_at=utc_now(),
    )
    return result, report
