"""Repository classification and AI-share banding (spec §10).

Hard rules encoded here:
- LIKELY_SHALLOW_OR_TEMPLATED requires ai_slop_risk >= 70 AND confidence >= 70
  AND a recorded counter-evidence review (fairness rule §11);
- exact AI-generated-code percentages are rejected outright — only the
  conservative evidence-based ranges (or INSUFFICIENT_EVIDENCE) may be stated;
- popularity (distribution_strength) never feeds a quality classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from loop_engineering.domain.errors import ProvenanceRuleViolation
from loop_engineering.use_cases.github_authority_audit.rubric import DimensionScore, RepoScores

PRIMARY_CLASSIFICATIONS = (
    "SUBSTANTIVE_TECHNICAL_BUILD",
    "AI_ASSISTED_BUT_MEANINGFUL",
    "EDUCATIONAL_OR_CURATED_VALUE",
    "DISTRIBUTION_LED_ASSET",
    "LIKELY_SHALLOW_OR_TEMPLATED",
    "INSUFFICIENT_EVIDENCE",
)

AI_SHARE_RANGES = ("0-25", "25-50", "50-75", "75-100", "INSUFFICIENT_EVIDENCE")

SLOP_RISK_FLOOR = 70.0
SLOP_CONFIDENCE_FLOOR = 70.0
MIN_CLASSIFICATION_CONFIDENCE = 40.0

_EXACT_PCT_PATTERN = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s*%\s*(?:of\s+the\s+code\s+is\s+)?ai[- ]"
    r"(?:generated|written|authored)",
    re.IGNORECASE,
)


@dataclass
class CounterEvidenceReview:
    """Explicit record that counter-evidence was searched for and considered."""

    reviewed: bool
    strongest_counter_evidence: list[str] = field(default_factory=list)
    review_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewed": self.reviewed,
            "strongest_counter_evidence": list(self.strongest_counter_evidence),
            "review_notes": self.review_notes,
        }


@dataclass
class RepoClassification:
    primary: str
    value_labels: list[str]
    rationale: str
    counter_evidence: CounterEvidenceReview | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "value_labels": list(self.value_labels),
            "rationale": self.rationale,
            "counter_evidence": self.counter_evidence.to_dict() if self.counter_evidence else None,
        }


def classify_repo(
    scores: RepoScores,
    counter_evidence: CounterEvidenceReview | None = None,
    slop_floor: float = SLOP_RISK_FLOOR,
) -> RepoClassification:
    """One primary classification; multiple value labels allowed."""
    labels: list[str] = []
    if scores.technical_proficiency >= 70 and scores.human_reasoning_evidence >= 55:
        labels.append("SUBSTANTIVE_TECHNICAL_BUILD")
    if scores.ai_assistance_likelihood >= 55 and (
        scores.technical_proficiency >= 50 or scores.educational_value >= 50
    ):
        labels.append("AI_ASSISTED_BUT_MEANINGFUL")
    if scores.educational_value >= 70:
        labels.append("EDUCATIONAL_OR_CURATED_VALUE")
    if scores.distribution_strength >= 70:
        labels.append("DISTRIBUTION_LED_ASSET")

    if scores.confidence < MIN_CLASSIFICATION_CONFIDENCE:
        return RepoClassification(
            primary="INSUFFICIENT_EVIDENCE",
            value_labels=labels,
            rationale=(
                f"confidence {scores.confidence:.0f} below the "
                f"{MIN_CLASSIFICATION_CONFIDENCE:.0f} floor for any classification"
            ),
            counter_evidence=counter_evidence,
        )

    if scores.ai_slop_risk >= slop_floor and scores.confidence >= SLOP_CONFIDENCE_FLOOR:
        # Negative classification demands a recorded counter-evidence review.
        if counter_evidence is None or not counter_evidence.reviewed:
            return RepoClassification(
                primary="INSUFFICIENT_EVIDENCE",
                value_labels=labels,
                rationale=(
                    f"ai_slop_risk {scores.ai_slop_risk:.0f} and confidence "
                    f"{scores.confidence:.0f} meet the shallow/templated thresholds, but no "
                    "counter-evidence review was recorded; negative classification withheld"
                ),
                counter_evidence=counter_evidence,
            )
        return RepoClassification(
            primary="LIKELY_SHALLOW_OR_TEMPLATED",
            value_labels=labels,
            rationale=(
                f"ai_slop_risk {scores.ai_slop_risk:.0f} >= {slop_floor:.0f} with "
                f"confidence {scores.confidence:.0f} >= {SLOP_CONFIDENCE_FLOOR:.0f}; "
                "counter-evidence reviewed and recorded"
            ),
            counter_evidence=counter_evidence,
        )

    for candidate in (
        "SUBSTANTIVE_TECHNICAL_BUILD",
        "AI_ASSISTED_BUT_MEANINGFUL",
        "EDUCATIONAL_OR_CURATED_VALUE",
        "DISTRIBUTION_LED_ASSET",
    ):
        if candidate in labels:
            if candidate == "DISTRIBUTION_LED_ASSET" and scores.technical_proficiency >= 50:
                continue  # popularity never outranks demonstrated substance
            return RepoClassification(
                primary=candidate,
                value_labels=labels,
                rationale=f"highest-priority label meeting its criteria: {candidate}",
                counter_evidence=counter_evidence,
            )

    return RepoClassification(
        primary="INSUFFICIENT_EVIDENCE",
        value_labels=labels,
        rationale="no classification criteria met with sufficient evidence",
        counter_evidence=counter_evidence,
    )


def band_ai_share(likelihood: float, confidence: float) -> str:
    """Conservative estimated_ai_assisted_code_share_range — never a precise number."""
    if confidence < 50.0:
        return "INSUFFICIENT_EVIDENCE"
    if likelihood >= 75.0:
        return "75-100"
    if likelihood >= 50.0:
        return "50-75"
    if likelihood >= 25.0:
        return "25-50"
    return "0-25"


def assert_no_exact_ai_percentage(text: str) -> None:
    """Reject any exact AI-authorship percentage presented as fact (PD-04/PD-08)."""
    match = _EXACT_PCT_PATTERN.search(text)
    if match:
        raise ProvenanceRuleViolation(
            f"exact AI-authorship percentage asserted without provenance evidence: "
            f"{match.group(0)!r}; only ranges {AI_SHARE_RANGES} are permitted"
        )


def ai_share_statement(likelihood: float, confidence: float, evidence: str) -> dict[str, Any]:
    """The only sanctioned way to state AI-assisted share."""
    band = band_ai_share(likelihood, confidence)
    statement = {
        "estimated_ai_assisted_code_share_range": band,
        "confidence": round(confidence, 1),
        "evidence_and_counter_evidence": evidence,
        "note": (
            "exact AI-generated code percentage is not inferable from public code "
            "without provenance logs; this range is a conservative signal-based estimate "
            "and is not the slop score"
        ),
    }
    assert_no_exact_ai_percentage(str(statement))
    return statement


def dimension_evidence(dims: list[DimensionScore]) -> list[dict[str, Any]]:
    return [d.to_dict() for d in dims]
