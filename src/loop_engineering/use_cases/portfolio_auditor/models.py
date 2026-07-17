"""Evidence model, verdict vocabulary, and the scoring/confidence model.

Everything serializes to plain dicts (file-backed JSON/JSONL/YAML state is a
locked constraint). Findings reuse the shared :class:`EvidenceItem` whose
``origin`` field is the independence key used for corroboration and for
redaction of private origins.

The verdict enums here are the single source of truth for the classification
vocabularies the digest-locked ``ProductDecisionContract`` also pins; the
contract tests assert the two agree.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from loop_engineering.domain.models import EvidenceItem

CONFIDENCE_MIN = 0
CONFIDENCE_MAX = 100


class RecommendationVerdict(enum.StrEnum):
    """The five portfolio decisions the auditor recommends per repository."""

    FIX = "FIX"
    SHOWCASE = "SHOWCASE"
    CONSOLIDATE = "CONSOLIDATE"
    REBUILD = "REBUILD"
    KEEP_AS_IS = "KEEP_AS_IS"


class AISlopVerdict(enum.StrEnum):
    """Repository-level AI-slop verdict — three values, never a personal judgment."""

    AI_SLOP = "AI_SLOP"
    NOT_AI_SLOP = "NOT_AI_SLOP"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class BusinessAccuracyVerdict(enum.StrEnum):
    """Claim-to-evidence grade for business/product accuracy."""

    PROVEN = "PROVEN"
    LIKELY = "LIKELY"
    NOT_PROVEN = "NOT_PROVEN"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RemediationClosure(enum.StrEnum):
    """Post-remediation status of an originally-recorded finding."""

    FIXED = "FIXED"
    PARTIALLY_FIXED = "PARTIALLY_FIXED"
    NOT_FIXED = "NOT_FIXED"
    REGRESSED = "REGRESSED"


class InspectionDepth(enum.StrEnum):
    BROAD = "BROAD"
    DEEP = "DEEP"


class RepoVisibility(enum.StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class Severity(enum.StrEnum):
    BLOCKING = "BLOCKING"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


#: Lower rank == more severe (used for deterministic sorting).
SEVERITY_RANK: dict[Severity, int] = {
    Severity.BLOCKING: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def severity_rank(severity: Severity) -> int:
    return SEVERITY_RANK[severity]


def clamp_confidence(value: float) -> int:
    """Clamp any confidence into the closed 0..100 integer band."""
    return max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, int(value)))


@dataclass
class Finding:
    """One material audit finding.

    Records exactly the fields the product contract requires for every finding:
    id, evidence, confidence, severity, affected capability, reasoning, and a
    remediation recommendation. ``dimension`` and ``repository`` locate it.
    """

    finding_id: str
    repository: str
    dimension: str
    summary: str
    evidence: list[EvidenceItem]
    confidence: int
    severity: Severity
    affected_capability: str
    reasoning: str
    remediation_recommendation: str
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.confidence = clamp_confidence(self.confidence)

    @property
    def is_blocking(self) -> bool:
        return self.severity is Severity.BLOCKING

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "repository": self.repository,
            "dimension": self.dimension,
            "summary": self.summary,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "severity": self.severity.value,
            "affected_capability": self.affected_capability,
            "reasoning": self.reasoning,
            "remediation_recommendation": self.remediation_recommendation,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(
            finding_id=str(data["finding_id"]),
            repository=str(data["repository"]),
            dimension=str(data["dimension"]),
            summary=str(data["summary"]),
            evidence=[EvidenceItem.from_dict(e) for e in data.get("evidence", [])],
            confidence=int(data["confidence"]),
            severity=Severity(data["severity"]),
            affected_capability=str(data["affected_capability"]),
            reasoning=str(data["reasoning"]),
            remediation_recommendation=str(data["remediation_recommendation"]),
            tags=[str(t) for t in data.get("tags", [])],
        )


def blocking_findings(findings: list[Finding]) -> list[Finding]:
    """The subset that blocks delivery / auto-merge (BLOCKING severity)."""
    return [f for f in findings if f.is_blocking]


def must_surface(finding: Finding, high_confidence_floor: int) -> bool:
    """Guard for "a numeric score must never override a material finding".

    A finding that is both *material* (BLOCKING or HIGH severity) and
    *high-confidence* (>= floor) must always be surfaced regardless of any
    numeric prioritization score.
    """
    material = severity_rank(finding.severity) <= severity_rank(Severity.HIGH)
    return material and finding.confidence >= high_confidence_floor


def prioritization_score(
    strategic_importance: float,
    severity_weight: float,
    authority_impact: float,
    confidence: float,
    remediation_effort: float,
) -> float:
    """Deterministic priority.

    ``Priority = strategic * severity * authority * confidence / effort``.

    The score *ranks* remediation work; it never overrides a material
    high-confidence finding (see :func:`must_surface`).
    """
    if remediation_effort <= 0:
        raise ValueError("remediation_effort must be > 0 (it is the denominator)")
    return (strategic_importance * severity_weight * authority_impact * confidence) / (
        remediation_effort
    )
