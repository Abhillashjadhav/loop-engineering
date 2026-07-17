"""Milestone 1 — evidence model, verdict vocabulary, scoring/confidence model.

Findings reuse the shared ``EvidenceItem`` (whose ``origin`` field is the
independence key), so corroboration and redaction stay consistent with the
rest of the Loop Engineering spine.
"""

from __future__ import annotations

import pytest

from loop_engineering.domain.models import EvidenceItem
from loop_engineering.use_cases.portfolio_auditor import models as m


def _evidence(origin: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev-{origin}",
        source_url=f"repo://acme/demo/{origin}",
        origin=origin,
        retrieved_at="2026-07-17T00:00:00+00:00",
        content_hash="sha256:deadbeef",
        excerpt="…",
    )


def test_verdict_vocabularies() -> None:
    assert {v.value for v in m.RecommendationVerdict} == {
        "FIX",
        "SHOWCASE",
        "CONSOLIDATE",
        "REBUILD",
        "KEEP_AS_IS",
    }
    assert {v.value for v in m.AISlopVerdict} == {
        "AI_SLOP",
        "NOT_AI_SLOP",
        "INSUFFICIENT_EVIDENCE",
    }
    assert {v.value for v in m.BusinessAccuracyVerdict} == {
        "PROVEN",
        "LIKELY",
        "NOT_PROVEN",
        "CONTRADICTED",
        "INSUFFICIENT_EVIDENCE",
    }
    assert {v.value for v in m.RemediationClosure} == {
        "FIXED",
        "PARTIALLY_FIXED",
        "NOT_FIXED",
        "REGRESSED",
    }
    assert {v.value for v in m.InspectionDepth} == {"BROAD", "DEEP"}
    assert {v.value for v in m.RepoVisibility} == {"PUBLIC", "PRIVATE"}


def test_finding_round_trips() -> None:
    f = m.Finding(
        finding_id="F-001",
        repository="acme/demo",
        dimension="security",
        summary="Hardcoded token in config",
        evidence=[_evidence("source_code"), _evidence("commit_history")],
        confidence=88,
        severity=m.Severity.BLOCKING,
        affected_capability="authentication",
        reasoning="Token literal present and committed.",
        remediation_recommendation="Remove secret; rotate; add secret scan.",
    )
    restored = m.Finding.from_dict(f.to_dict())
    assert restored == f
    assert restored.evidence[0].origin == "source_code"


def test_clamp_confidence_bounds() -> None:
    assert m.clamp_confidence(-5) == 0
    assert m.clamp_confidence(140) == 100
    assert m.clamp_confidence(73) == 73


def test_finding_confidence_is_clamped_on_construction() -> None:
    f = m.Finding(
        finding_id="F",
        repository="r",
        dimension="d",
        summary="s",
        evidence=[],
        confidence=250,
        severity=m.Severity.LOW,
        affected_capability="c",
        reasoning="x",
        remediation_recommendation="y",
    )
    assert f.confidence == 100


def test_severity_rank_orders_blocking_first() -> None:
    order = sorted(
        [m.Severity.LOW, m.Severity.BLOCKING, m.Severity.MEDIUM, m.Severity.HIGH],
        key=m.severity_rank,
    )
    assert order[0] is m.Severity.BLOCKING


def test_blocking_findings_selected() -> None:
    findings = [
        m.Finding("a", "r", "d", "s", [], 90, m.Severity.BLOCKING, "c", "x", "y"),
        m.Finding("b", "r", "d", "s", [], 90, m.Severity.LOW, "c", "x", "y"),
    ]
    blocking = m.blocking_findings(findings)
    assert [f.finding_id for f in blocking] == ["a"]


def test_prioritization_formula() -> None:
    # Priority = strategic × severity × authority × confidence ÷ effort
    score = m.prioritization_score(
        strategic_importance=5,
        severity_weight=4,
        authority_impact=3,
        confidence=80,
        remediation_effort=2,
    )
    assert score == pytest.approx((5 * 4 * 3 * 80) / 2)


def test_prioritization_rejects_zero_effort() -> None:
    # Effort in the denominator must be guarded; zero effort would divide by zero.
    with pytest.raises(ValueError):
        m.prioritization_score(1, 1, 1, 50, 0)


def test_material_high_confidence_finding_must_surface_regardless_of_score() -> None:
    # "A numeric score must never override a material high-confidence finding."
    blocker = m.Finding("a", "r", "security", "leak", [], 95, m.Severity.BLOCKING, "c", "x", "y")
    minor = m.Finding("b", "r", "style", "nit", [], 95, m.Severity.LOW, "c", "x", "y")
    assert m.must_surface(blocker, high_confidence_floor=70) is True
    assert m.must_surface(minor, high_confidence_floor=70) is False
