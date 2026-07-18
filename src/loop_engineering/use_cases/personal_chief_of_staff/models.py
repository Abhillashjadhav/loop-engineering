"""Typed records for the Personal Chief of Staff (locked data model).

Every Task carries its source and confidence — an inferred task can never
lose its provenance. Enumerations are closed so a typo cannot silently
invent a category. Records are frozen dataclasses with deterministic
``to_dict`` for byte-stable serialization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    EMAIL = "email"
    CALENDAR = "calendar"
    GITHUB = "github"
    DRIVE_DOC = "drive_doc"
    CHAT_CONTEXT = "chat_context"
    PROJECT_CHECKPOINT = "project_checkpoint"
    MANUAL = "manual"


class Origin(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class TaskStatus(StrEnum):
    INBOX = "inbox"  # newly inferred, below confirm threshold
    ACTIVE = "active"
    BLOCKED = "blocked"
    WAITING = "waiting_on_other"
    DONE = "done"
    DROPPED = "dropped"


class Energy(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Flexibility(StrEnum):
    FIXED = "fixed"  # external attendees / hard commitment
    MOVABLE = "movable"  # solo, can be rescheduled
    FOCUS_BLOCK = "focus_block"  # created by this system


class AdapterMode(StrEnum):
    LIVE = "LIVE"
    FIXTURE = "FIXTURE"
    MANUAL_IMPORT = "MANUAL_IMPORT"
    UNAVAILABLE = "UNAVAILABLE"


class ApprovalRequirement(StrEnum):
    NONE = "none"  # safe action, auto-executable
    SCHEDULE_APPROVAL = "schedule_approval"  # one approval for the proposed schedule
    EXPLICIT = "explicit"  # per-action explicit approval (send/publish/cancel/…)


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    BLOCKED_PROHIBITED = "blocked_prohibited"


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    outcome: str
    priority: int
    status: str
    source: str
    approved_at: str
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSource:
    """Immutable provenance for a task — never dropped through dedup/merge."""

    source_type: SourceType
    source_reference: str  # message id, event id, repo#pr, file path, "manual"
    source_excerpt: str  # exact supporting text
    inferred_or_explicit: Origin
    confidence: float  # 0..1
    inference_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["inferred_or_explicit"] = self.inferred_or_explicit.value
        return d


@dataclass
class Task:
    id: str
    title: str
    description: str
    sources: list[TaskSource]
    goal_ids: list[str] = field(default_factory=list)
    project: str = ""
    deadline: str | None = None  # ISO date; None = no deadline (never invented)
    urgency: int = 0  # 0..5
    impact: int = 0  # 0..5
    strategic_value: int = 0  # 0..5
    external_commitment: bool = False
    estimated_minutes: int = 30
    energy: Energy = Energy.MEDIUM
    dependency_ids: list[str] = field(default_factory=list)
    blocked_by: str = ""  # free text reason if blocked
    waiting_on: str = ""  # person we're waiting on
    status: TaskStatus = TaskStatus.ACTIVE
    evidence_of_completion: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def confidence(self) -> float:
        """A task is as confident as its most confident supporting source."""
        return max((s.confidence for s in self.sources), default=0.0)

    @property
    def is_inferred(self) -> bool:
        return all(s.inferred_or_explicit is Origin.INFERRED for s in self.sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": round(self.confidence, 3),
            "inferred_or_explicit": (
                Origin.INFERRED.value if self.is_inferred else Origin.EXPLICIT.value
            ),
            "goal_ids": list(self.goal_ids),
            "project": self.project,
            "deadline": self.deadline,
            "urgency": self.urgency,
            "impact": self.impact,
            "strategic_value": self.strategic_value,
            "external_commitment": self.external_commitment,
            "estimated_minutes": self.estimated_minutes,
            "energy": self.energy.value,
            "dependency_ids": list(self.dependency_ids),
            "blocked_by": self.blocked_by,
            "waiting_on": self.waiting_on,
            "status": self.status.value,
            "evidence_of_completion": self.evidence_of_completion,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class CalendarItem:
    event_id: str
    title: str
    start: str  # ISO datetime
    end: str  # ISO datetime
    attendees: list[str] = field(default_factory=list)
    flexibility: Flexibility = Flexibility.FIXED
    source: SourceType = SourceType.CALENDAR
    preparation_tasks: list[str] = field(default_factory=list)
    followup_tasks: list[str] = field(default_factory=list)

    @property
    def has_external_attendees(self) -> bool:
        return len([a for a in self.attendees if a]) > 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["flexibility"] = self.flexibility.value
        d["source"] = self.source.value
        return d


@dataclass(frozen=True)
class DecisionCheckpoint:
    timestamp: str
    approved_decisions: list[str] = field(default_factory=list)
    rejected_ideas: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    context_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionProposal:
    id: str
    action_type: str  # gmail_draft, focus_block, github_issue, reminder, ...
    target: str
    reason: str
    expected_result: str
    risk: str  # low | medium | high
    approval_requirement: ApprovalRequirement
    status: ProposalStatus = ProposalStatus.PROPOSED
    execution_evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "target": self.target,
            "reason": self.reason,
            "expected_result": self.expected_result,
            "risk": self.risk,
            "approval_requirement": self.approval_requirement.value,
            "status": self.status.value,
            "execution_evidence": self.execution_evidence,
        }
