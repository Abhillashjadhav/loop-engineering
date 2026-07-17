"""Milestone 1 — immutable, digest-locked ProductDecisionContract.

The Portfolio Auditor reuses the Loop Engineering candidate-freezing mechanism
(``contracts/goal_contract.py``) rather than duplicating it; these tests pin the
auditor-specific contract shape, its locked product decisions, and the policy
accessors that later milestones consume.
"""

from __future__ import annotations

import copy

import pytest

from loop_engineering.domain.errors import ContractViolation
from loop_engineering.use_cases.portfolio_auditor import contract as pc


def test_shipped_contract_loads_and_verifies() -> None:
    c = pc.load_default()
    assert c["contract_id"] == "github-portfolio-auditor-v1"
    assert c["version"] >= 1
    # A shipped contract must be locked and internally consistent.
    pc.verify_integrity(c)
    pc.validate(c)


def test_digest_detects_tampering() -> None:
    c = pc.load_default()
    tampered = copy.deepcopy(c)
    tampered["north_star"] = "something else entirely"
    with pytest.raises(ContractViolation):
        pc.verify_integrity(tampered)


def test_lock_is_deterministic_and_excludes_digest_field() -> None:
    c = pc.load_default()
    body = {k: v for k, v in c.items() if k != pc.DIGEST_FIELD}
    relocked = pc.lock(body)
    assert relocked[pc.DIGEST_FIELD] == c[pc.DIGEST_FIELD]


def test_validate_rejects_missing_required_section() -> None:
    c = pc.load_default()
    broken = copy.deepcopy(c)
    del broken["remediation_policy"]
    with pytest.raises(ContractViolation):
        pc.validate(broken)


def test_amend_creates_new_version_with_trail() -> None:
    c = pc.load_default()
    amended = pc.amend(
        c,
        {"north_star": c["north_star"] + " (clarified)"},
        approved_by="abhillash",
        reason="wording clarification approved by operator",
    )
    assert amended["version"] == c["version"] + 1
    assert amended["amendments"][-1]["previous_digest"] == c[pc.DIGEST_FIELD]
    assert amended["amendments"][-1]["approved_by"] == "abhillash"
    pc.verify_integrity(amended)


def test_amend_requires_approver_and_reason() -> None:
    c = pc.load_default()
    with pytest.raises(ContractViolation):
        pc.amend(c, {"north_star": "x"}, approved_by="  ", reason="r")
    with pytest.raises(ContractViolation):
        pc.amend(c, {"north_star": "x"}, approved_by="a", reason="")


def test_amend_rejects_structural_fields() -> None:
    c = pc.load_default()
    for field in ("contract_id", "version", pc.DIGEST_FIELD, "amendments"):
        with pytest.raises(ContractViolation):
            pc.amend(c, {field: "hack"}, approved_by="a", reason="r")


# --- locked policy content the rest of the system depends on --------------


def test_ai_slop_verdict_vocabulary_is_exactly_three() -> None:
    assert pc.ai_slop_verdicts(pc.load_default()) == [
        "AI_SLOP",
        "NOT_AI_SLOP",
        "INSUFFICIENT_EVIDENCE",
    ]


def test_business_accuracy_scale_is_the_five_locked_grades() -> None:
    assert pc.business_accuracy_scale(pc.load_default()) == [
        "PROVEN",
        "LIKELY",
        "NOT_PROVEN",
        "CONTRADICTED",
        "INSUFFICIENT_EVIDENCE",
    ]


def test_recommendation_verdicts_are_the_five_decisions() -> None:
    assert set(pc.recommendation_verdicts(pc.load_default())) == {
        "FIX",
        "SHOWCASE",
        "CONSOLIDATE",
        "REBUILD",
        "KEEP_AS_IS",
    }


def test_auto_merge_required_gates_cover_the_locked_conditions() -> None:
    gates = pc.auto_merge_required_gates(pc.load_default())
    # Every locked auto-merge precondition must be present as a named gate.
    for needed in (
        "within_approved_scope",
        "no_unresolved_product_decision_change",
        "tests_first_where_applicable",
        "substantive_ci_green",
        "independent_review_approve",
        "no_blocking_finding_remaining",
        "post_patch_audit_passes",
        "bound_to_inspected_commit",
        "does_not_weaken_gates",
    ):
        assert needed in gates, needed


def test_auto_merge_forbidden_actions_are_blocked() -> None:
    forbidden = pc.auto_merge_forbidden_actions(pc.load_default())
    for needed in (
        "major_architecture_rewrite",
        "product_scope_change",
        "business_claim_change_needs_user",
        "destructive_archival_or_deletion",
        "repository_consolidation",
        "insufficient_evidence",
        "weakens_validation",
        "hides_or_deletes_failed_evidence",
    ):
        assert needed in forbidden, needed


def test_ai_slop_hard_verdict_is_confidence_gated() -> None:
    policy = pc.ai_slop_policy(pc.load_default())
    # A hard AI_SLOP verdict must require a high confidence floor and counter-evidence.
    assert policy["hard_verdict_min_confidence"] >= 70
    assert policy["require_counter_evidence_review"] is True
    # Forbidden sole bases must be recorded.
    for basis in (
        "writing_style",
        "disclosed_ai_assistance",
        "commit_volume",
        "repository_size",
        "generated_file_count",
        "lack_of_popularity",
    ):
        assert basis in policy["forbidden_sole_bases"], basis


def test_scope_never_authorizes_merging_feature_branch() -> None:
    c = pc.load_default()
    rp = c["remediation_policy"]
    # The auto-merge authority is explicitly scoped to future remediation PRs,
    # never the auditor feature branch itself.
    assert rp["auto_merge_scope"] == "future_remediation_prs_only"
    assert rp["never_auto_merges_the_auditor_feature_branch"] is True
