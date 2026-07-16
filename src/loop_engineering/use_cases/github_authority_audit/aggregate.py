"""Person-level aggregation (spec §10).

Produces both a repository-count-weighted and an active-code-weighted
distribution so one highly starred repo can never overwrite the portfolio,
and answers the underlying question with a bounded verdict enum plus an
explicit "what cannot be concluded" list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from loop_engineering.use_cases.github_authority_audit.classify import RepoClassification
from loop_engineering.use_cases.github_authority_audit.inventory import RepoRecord
from loop_engineering.use_cases.github_authority_audit.rubric import RepoScores

PERSON_VERDICTS = (
    "TECHNICAL_DEPTH_DOMINANT",
    "EDUCATION_AND_DISTRIBUTION_WITH_TECHNICAL_DEPTH",
    "DISTRIBUTION_OR_CURATION_DOMINANT",
    "MIXED_PORTFOLIO",
    "INSUFFICIENT_EVIDENCE",
)

ACTIVE_MAINTENANCE_WINDOW_DAYS = 548  # ~18 months


@dataclass
class RepoAssessment:
    record: RepoRecord
    scores: RepoScores
    classification: RepoClassification

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.record.name,
            "kind": self.record.kind,
            "scores": self.scores.to_dict(),
            "classification": self.classification.to_dict(),
        }


@dataclass
class PersonAssessment:
    subject: str
    login: str
    repo_count_weighted: dict[str, float]
    active_code_weighted: dict[str, float]
    aggregate_scores: dict[str, float]
    verdict: str
    cannot_conclude: list[str]
    fork_count: int
    analyzed_count: int
    excluded_forks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "login": self.login,
            "repo_count_weighted": dict(self.repo_count_weighted),
            "active_code_weighted": dict(self.active_code_weighted),
            "aggregate_scores": dict(self.aggregate_scores),
            "verdict": self.verdict,
            "cannot_conclude": list(self.cannot_conclude),
            "fork_count": self.fork_count,
            "analyzed_count": self.analyzed_count,
            "excluded_forks": list(self.excluded_forks),
        }


def _is_actively_maintained(record: RepoRecord, as_of: datetime) -> bool:
    if not record.pushed_at:
        return False
    try:
        pushed = datetime.fromisoformat(record.pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if pushed.tzinfo is None:
        pushed = pushed.replace(tzinfo=UTC)
    return as_of - pushed <= timedelta(days=ACTIVE_MAINTENANCE_WINDOW_DAYS)


def _distribution(pairs: list[tuple[str, float]]) -> dict[str, float]:
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return {}
    acc: dict[str, float] = {}
    for label, weight in pairs:
        acc[label] = acc.get(label, 0.0) + weight
    return {label: round(100.0 * w / total, 1) for label, w in sorted(acc.items())}


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def aggregate_person(
    subject: str,
    login: str,
    assessments: list[RepoAssessment],
    fork_names: list[str],
    as_of: datetime | None = None,
) -> PersonAssessment:
    """Aggregate per-repo assessments (forks must already be excluded)."""
    now = as_of or datetime.now(UTC)

    count_pairs = [(a.classification.primary, 1.0) for a in assessments]
    active_pairs: list[tuple[str, float]] = []
    for a in assessments:
        r = a.record
        if r.kind == "original" and r.commit_count > 0 and _is_actively_maintained(r, now):
            active_pairs.append((a.classification.primary, float(min(r.commit_count, 500))))

    scores = {
        "substantive_technical_depth": _mean([a.scores.technical_proficiency for a in assessments]),
        "human_reasoning_evidence": _mean([a.scores.human_reasoning_evidence for a in assessments]),
        "educational_strength": _mean([a.scores.educational_value for a in assessments]),
        "distribution_strength": _mean([a.scores.distribution_strength for a in assessments]),
        "ai_assisted_creation_likelihood": _mean(
            [a.scores.ai_assistance_likelihood for a in assessments]
        ),
        "shallow_templated_share_pct": _distribution(count_pairs).get(
            "LIKELY_SHALLOW_OR_TEMPLATED", 0.0
        ),
        "claim_evidence_integrity": _mean([a.scores.claim_evidence_integrity for a in assessments]),
        "confidence": _mean([a.scores.confidence for a in assessments]),
    }

    verdict = _person_verdict(scores, len(assessments))

    cannot_conclude = [
        "private intent or motivation behind any repository",
        "exact human vs AI authorship of any file (no provenance logs available)",
        "private or unpublished contributions outside the public portfolio",
        "whether the person 'understands GenAI' — repository evidence alone cannot establish "
        "a person's understanding",
    ]

    return PersonAssessment(
        subject=subject,
        login=login,
        repo_count_weighted=_distribution(count_pairs),
        active_code_weighted=_distribution(active_pairs),
        aggregate_scores=scores,
        verdict=verdict,
        cannot_conclude=cannot_conclude,
        fork_count=len(fork_names),
        analyzed_count=len(assessments),
        excluded_forks=list(fork_names),
    )


def _person_verdict(scores: dict[str, float], analyzed_count: int) -> str:
    if analyzed_count == 0 or scores["confidence"] < 40.0:
        return "INSUFFICIENT_EVIDENCE"
    tech = scores["substantive_technical_depth"]
    edu = scores["educational_strength"]
    dist = scores["distribution_strength"]
    if tech >= 70.0 and tech >= edu and tech >= dist:
        return "TECHNICAL_DEPTH_DOMINANT"
    if tech >= 55.0 and (edu >= 60.0 or dist >= 60.0):
        return "EDUCATION_AND_DISTRIBUTION_WITH_TECHNICAL_DEPTH"
    if (edu >= 60.0 or dist >= 60.0) and tech < 55.0:
        return "DISTRIBUTION_OR_CURATION_DOMINANT"
    return "MIXED_PORTFOLIO"
