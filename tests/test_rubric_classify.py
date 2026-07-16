"""Rubric/classification hard rules: forks out, popularity is not quality,
AI assistance is not slop, negative labels need counter-evidence + confidence,
exact AI percentages rejected."""

from __future__ import annotations

import pytest
from tests.conftest import GITHUB_FIXTURES

from loop_engineering.domain.errors import ProvenanceRuleViolation
from loop_engineering.use_cases.github_authority_audit.aggregate import (
    RepoAssessment,
    aggregate_person,
)
from loop_engineering.use_cases.github_authority_audit.classify import (
    CounterEvidenceReview,
    ai_share_statement,
    assert_no_exact_ai_percentage,
    band_ai_share,
    classify_repo,
)
from loop_engineering.use_cases.github_authority_audit.datasource import FixtureDataSource
from loop_engineering.use_cases.github_authority_audit.inventory import build_inventory
from loop_engineering.use_cases.github_authority_audit.rubric import (
    RepoScores,
    derive_scores,
    score_dimensions,
)


def scores(**overrides: float) -> RepoScores:
    base = {
        "human_reasoning_evidence": 50.0,
        "technical_proficiency": 50.0,
        "ai_assistance_likelihood": 10.0,
        "ai_assistance_confidence": 100.0,
        "ai_slop_risk": 30.0,
        "educational_value": 50.0,
        "distribution_strength": 10.0,
        "claim_evidence_integrity": 80.0,
        "confidence": 90.0,
    }
    base.update(overrides)
    return RepoScores(**base)  # type: ignore[arg-type]


def reviewed() -> CounterEvidenceReview:
    return CounterEvidenceReview(reviewed=True, strongest_counter_evidence=["works in principle"])


def templater_inventory():  # type: ignore[no-untyped-def]
    ds = FixtureDataSource(GITHUB_FIXTURES)
    return build_inventory("synthetic-templater", ds.repositories("synthetic-templater"))


def test_forks_excluded_from_authored_scoring() -> None:
    ds = FixtureDataSource(GITHUB_FIXTURES)
    inv = build_inventory("synthetic-builder", ds.repositories("synthetic-builder"))
    authored_names = {r.name for r in inv.authored}
    assert "upstream-sdk" not in authored_names  # the fork
    assert "upstream-sdk" in {r.name for r in inv.forks}  # reported separately
    assert "legacy-experiments" in authored_names  # archived own work still authored


def test_pagination_all_pages_retrieved() -> None:
    ds = FixtureDataSource(GITHUB_FIXTURES)
    names = {r["name"] for r in ds.repositories("synthetic-builder")}
    assert "data-pipeline" in names  # lives on page-2


def test_popularity_is_not_quality() -> None:
    # Identical quality signals, wildly different stars -> same classification,
    # same technical score; only distribution_strength differs.
    low = scores(distribution_strength=5.0)
    high = scores(distribution_strength=95.0)
    assert classify_repo(low).primary == classify_repo(high).primary
    assert low.technical_proficiency == high.technical_proficiency
    # High distribution + low tech must not become a quality claim:
    dist_led = classify_repo(
        scores(distribution_strength=95.0, technical_proficiency=30.0, educational_value=20.0)
    )
    assert dist_led.primary == "DISTRIBUTION_LED_ASSET"


def test_ai_assistance_separated_from_slop() -> None:
    # Heavy AI assistance with real substance is NOT slop.
    assisted = classify_repo(
        scores(
            ai_assistance_likelihood=85.0,
            technical_proficiency=75.0,
            human_reasoning_evidence=60.0,
            ai_slop_risk=25.0,
        )
    )
    assert assisted.primary == "SUBSTANTIVE_TECHNICAL_BUILD"
    assert "AI_ASSISTED_BUT_MEANINGFUL" in assisted.value_labels


def test_negative_classification_requires_thresholds_and_counter_evidence() -> None:
    # risk below 70 -> never LIKELY_SHALLOW
    assert (
        classify_repo(scores(ai_slop_risk=69.0), reviewed()).primary
        != "LIKELY_SHALLOW_OR_TEMPLATED"
    )
    # confidence below 70 -> INSUFFICIENT_EVIDENCE, not a negative label
    assert (
        classify_repo(scores(ai_slop_risk=90.0, confidence=60.0), reviewed()).primary
        != "LIKELY_SHALLOW_OR_TEMPLATED"
    )
    # thresholds met but no counter-evidence review -> withheld
    withheld = classify_repo(scores(ai_slop_risk=90.0), None)
    assert withheld.primary == "INSUFFICIENT_EVIDENCE"
    assert "counter-evidence" in withheld.rationale
    # everything present -> negative classification with recorded counter-evidence
    negative = classify_repo(scores(ai_slop_risk=90.0), reviewed())
    assert negative.primary == "LIKELY_SHALLOW_OR_TEMPLATED"
    assert negative.counter_evidence is not None
    assert negative.counter_evidence.strongest_counter_evidence


def test_low_confidence_blocks_all_classification() -> None:
    result = classify_repo(scores(confidence=20.0))
    assert result.primary == "INSUFFICIENT_EVIDENCE"


def test_exact_ai_percentage_rejected() -> None:
    with pytest.raises(ProvenanceRuleViolation):
        assert_no_exact_ai_percentage("this repo is 87% AI-generated")
    with pytest.raises(ProvenanceRuleViolation):
        assert_no_exact_ai_percentage("roughly 42.5% ai written by tools")
    # ranges and unrelated percentages pass
    assert_no_exact_ai_percentage("estimated_ai_assisted_code_share_range: 50-75")
    assert_no_exact_ai_percentage("coverage rose 15% after refactoring")


def test_ai_share_banding() -> None:
    assert band_ai_share(90.0, 90.0) == "75-100"
    assert band_ai_share(60.0, 90.0) == "50-75"
    assert band_ai_share(30.0, 90.0) == "25-50"
    assert band_ai_share(5.0, 90.0) == "0-25"
    assert band_ai_share(90.0, 30.0) == "INSUFFICIENT_EVIDENCE"
    statement = ai_share_statement(90.0, 90.0, "signals")
    assert statement["estimated_ai_assisted_code_share_range"] == "75-100"
    assert "not inferable" in statement["note"]


def test_person_aggregation_both_weightings() -> None:
    inv = templater_inventory()
    assessments = []
    for record in inv.authored:
        dims = score_dimensions(record)
        s = derive_scores(record, dims)
        ce_raw = record.signals.get("counter_evidence_review")
        ce = (
            CounterEvidenceReview(
                reviewed=bool(ce_raw.get("reviewed")),
                strongest_counter_evidence=list(ce_raw.get("strongest_counter_evidence", [])),
            )
            if isinstance(ce_raw, dict)
            else None
        )
        assessments.append(
            RepoAssessment(record=record, scores=s, classification=classify_repo(s, ce))
        )
    person = aggregate_person(
        "Tee Templater", "synthetic-templater", assessments, [r.name for r in inv.forks]
    )
    assert person.repo_count_weighted["LIKELY_SHALLOW_OR_TEMPLATED"] == 40.0  # 2 of 5
    assert person.active_code_weighted  # active weighting exists and differs from count
    assert person.verdict in (
        "DISTRIBUTION_OR_CURATION_DOMINANT",
        "MIXED_PORTFOLIO",
    )
    assert any("cannot establish" in c or "authorship" in c for c in person.cannot_conclude)


def test_inaccessible_repo_recorded_honestly() -> None:
    inv = templater_inventory()
    hidden = [r for r in inv.records if r.name == "hidden-repo"]
    assert hidden and hidden[0].inaccessible
    assert hidden[0].inaccessible_reason
    assert "hidden-repo" not in {r.name for r in inv.authored}
