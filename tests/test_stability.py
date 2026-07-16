"""Loop 4: six-run comparison — disagreement preserved, never averaged."""

from __future__ import annotations

from typing import Any

from loop_engineering.domain.models import StabilityVariant
from loop_engineering.verification.loop4_stability import (
    RunFindings,
    compare_runs,
    verify_stability,
)


def six_runs(overrides: dict[StabilityVariant, dict[str, Any]] | None = None) -> list[RunFindings]:
    runs = []
    for variant in StabilityVariant:
        findings: dict[str, Any] = {"repo-x:primary": "SUBSTANTIVE_TECHNICAL_BUILD", "score": 90.0}
        if overrides and variant in overrides:
            findings.update(overrides[variant])
        runs.append(RunFindings(variant=variant, findings=findings))
    return runs


def test_all_stable_when_runs_agree() -> None:
    report = compare_runs(six_runs())
    assert report.unstable == {} and report.unresolved == []
    assert report.stable["repo-x:primary"] == "SUBSTANTIVE_TECHNICAL_BUILD"


def test_disagreement_preserved_not_averaged() -> None:
    report = compare_runs(
        six_runs({StabilityVariant.SKEPTICAL: {"repo-x:primary": "LIKELY_SHALLOW_OR_TEMPLATED"}})
    )
    assert "repo-x:primary" in report.unstable
    per_variant = report.unstable["repo-x:primary"]
    assert per_variant["skeptical"] == "LIKELY_SHALLOW_OR_TEMPLATED"
    assert per_variant["standard"] == "SUBSTANTIVE_TECHNICAL_BUILD"
    assert len(per_variant) == 6  # every variant's value preserved verbatim


def test_numeric_tolerance() -> None:
    report = compare_runs(six_runs({StabilityVariant.REORDERED_SOURCES: {"score": 93.0}}))
    assert "score" in report.stable  # within tolerance 5
    report = compare_runs(six_runs({StabilityVariant.REORDERED_SOURCES: {"score": 99.0}}))
    assert "score" in report.unstable


def test_partial_reporting_goes_to_unresolved() -> None:
    runs = six_runs()
    del runs[2].findings["score"]
    report = compare_runs(runs)
    assert any(u.startswith("score:") for u in report.unresolved)


def test_missing_variant_fails_verification() -> None:
    runs = six_runs()[:5]
    result, _ = verify_stability(runs)
    assert not result.passed
    assert "independent_replication" in (result.failure_reason or "")


def test_uncertainties_propagate() -> None:
    runs = six_runs()
    runs[3].uncertainties.append("borderline repo may flip")
    _, report = verify_stability(runs)
    assert any("borderline repo may flip" in u for u in report.unresolved)
