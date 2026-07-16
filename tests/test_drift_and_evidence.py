"""Loop 2 goal-drift math and Loop 3 evidence independence rules."""

from __future__ import annotations

from typing import Any

from tests.conftest import make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.models import (
    Claim,
    ClaimImpact,
    ClaimKind,
    EvidenceItem,
    PassCondition,
    SearchCoverage,
    Task,
)
from loop_engineering.planning.planner import coverage
from loop_engineering.verification import loop2_drift, loop3_evidence


def make_task(task_id: str, requirement: str) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement=requirement,
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
    )


def contract_with_scope(scope: list[str]) -> dict[str, Any]:
    return goal_contract.lock(make_contract_draft(scope=scope))


def test_drift_zero_when_aligned() -> None:
    contract = contract_with_scope(["r1", "r2"])
    tasks = [make_task("a", "r1"), make_task("b", "r2")]
    report = coverage(contract, tasks)
    assert report.drift_pct == 0.0
    result = loop2_drift.verify_plan(contract, tasks)
    assert result.passed


def test_orphan_task_is_drift() -> None:
    contract = contract_with_scope(["r1"])
    tasks = [make_task("a", "r1"), make_task("b", "sneaky new feature")]
    report = coverage(contract, tasks)
    assert report.orphan_task_ids == ["b"]
    assert report.drift_pct > 5.0
    assert not loop2_drift.verify_plan(contract, tasks).passed


def test_uncovered_requirement_is_drift() -> None:
    contract = contract_with_scope(["r1", "r2", "r3"])
    tasks = [make_task("a", "r1"), make_task("b", "r2")]
    report = coverage(contract, tasks)
    assert report.uncovered_requirements == ["r3"]
    assert not loop2_drift.verify_plan(contract, tasks).passed


def test_drift_calculation_value() -> None:
    # 1 orphan + 1 uncovered over (2 tasks + 2 requirements) = 50%
    contract = contract_with_scope(["r1", "r2"])
    tasks = [make_task("a", "r1"), make_task("b", "orphan-req")]
    assert coverage(contract, tasks).drift_pct == 50.0


# ---- loop 3 ----------------------------------------------------------------


def evidence(origin: str, eid: str = "e") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=eid,
        source_url=f"local://{origin}",
        origin=origin,
        retrieved_at="2026-07-16T00:00:00+00:00",
        content_hash="sha256:aa",
    )


def test_normal_claim_needs_two_independent_origins() -> None:
    claim = Claim(claim_id="c1", text="x", evidence=[evidence("source_code")])
    supported, reason = loop3_evidence.is_supported(claim)
    assert not supported and "1 independent origin" in reason
    claim.evidence.append(evidence("commit_history"))
    assert loop3_evidence.is_supported(claim)[0]


def test_same_origin_counts_once() -> None:
    claim = Claim(
        claim_id="c1",
        text="x",
        evidence=[evidence("source_code", "e1"), evidence("source_code", "e2")],
    )
    assert not loop3_evidence.is_supported(claim)[0]


def test_readme_alone_is_not_corroboration() -> None:
    claim = Claim(
        claim_id="c1",
        text="x",
        evidence=[evidence("readme", "e1"), evidence("self_description", "e2")],
    )
    supported, reason = loop3_evidence.is_supported(claim)
    assert not supported and "not independent corroboration" in reason


def test_high_impact_needs_three_origins() -> None:
    claim = Claim(
        claim_id="c1",
        text="x",
        impact=ClaimImpact.HIGH,
        evidence=[evidence("source_code"), evidence("commit_history")],
    )
    assert not loop3_evidence.is_supported(claim)[0]
    claim.evidence.append(evidence("file_listing"))
    assert loop3_evidence.is_supported(claim)[0]


def test_absence_claim_requires_complete_search_coverage() -> None:
    claim = Claim(
        claim_id="c1",
        text="repo has no tests",
        kind=ClaimKind.ABSENCE,
        evidence=[evidence("file_listing"), evidence("ci_config")],
    )
    assert not loop3_evidence.is_supported(claim)[0]
    claim.search_coverage = SearchCoverage(
        queries=["tests/"], scope_description="tree", complete=False
    )
    assert not loop3_evidence.is_supported(claim)[0]
    claim.search_coverage = SearchCoverage(
        queries=["tests/"], scope_description="tree", complete=True
    )
    assert loop3_evidence.is_supported(claim)[0]


def test_unsupported_claims_excluded_from_percentages_and_conflicts_visible() -> None:
    good = Claim(
        claim_id="good",
        text="x",
        evidence=[evidence("source_code"), evidence("commit_history")],
        conflicts=["source A and B disagree on release date"],
    )
    bad = Claim(claim_id="bad", text="y", evidence=[evidence("readme")])
    results, cov = loop3_evidence.verify_claims([good, bad])
    assert cov.total_claims == 2 and cov.supported_claims == 1
    assert cov.supported_pct == 50.0
    assert cov.unsupported_claim_ids == ["bad"]
    assert cov.conflicted_claim_ids == ["good"]
    assert {r.subject_id: r.passed for r in results} == {"good": True, "bad": False}
