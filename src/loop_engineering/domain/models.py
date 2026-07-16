"""Core dataclasses and enums.

Everything here serializes to plain dicts (JSON/JSONL/YAML) — file-backed state
is a locked V1 constraint.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any


class TaskStatus(enum.StrEnum):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REPAIRING = "REPAIRING"
    BLOCKED = "BLOCKED"
    SKIPPED_WITH_REASON = "SKIPPED_WITH_REASON"


#: Legal task state machine. Only VERIFIED satisfies completion.
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PLANNED: frozenset({TaskStatus.READY, TaskStatus.SKIPPED_WITH_REASON}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.BLOCKED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.EXECUTED, TaskStatus.FAILED, TaskStatus.BLOCKED}),
    TaskStatus.EXECUTED: frozenset({TaskStatus.VERIFIED, TaskStatus.FAILED}),
    TaskStatus.VERIFIED: frozenset(),
    TaskStatus.FAILED: frozenset(
        {TaskStatus.REPAIRING, TaskStatus.BLOCKED, TaskStatus.SKIPPED_WITH_REASON}
    ),
    TaskStatus.REPAIRING: frozenset({TaskStatus.READY, TaskStatus.BLOCKED}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.READY, TaskStatus.SKIPPED_WITH_REASON}),
    TaskStatus.SKIPPED_WITH_REASON: frozenset(),
}


class RunStatus(enum.StrEnum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"
    REPAIRING = "REPAIRING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class PassCondition:
    """Declarative pass condition, defined before execution, evaluated by the verifier."""

    type: str
    path: str | None = None
    text: str | None = None
    keys: list[str] = field(default_factory=list)
    digest: str | None = None
    count_key: str | None = None
    min: int | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return {k: v for k, v in raw.items() if v not in (None, [])}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PassCondition:
        return cls(
            type=str(data["type"]),
            path=data.get("path"),
            text=data.get("text"),
            keys=list(data.get("keys", [])),
            digest=data.get("digest"),
            count_key=data.get("count_key"),
            min=data.get("min"),
        )


@dataclass
class Task:
    """Atomic task: small enough to execute and verify independently (spec §5)."""

    task_id: str
    goal_requirement: str
    action: str
    expected_artifact: str
    evidence_required: list[str]
    pass_condition: PassCondition
    failure_condition: str
    dependencies: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    max_attempts: int = 3
    status: TaskStatus = TaskStatus.PLANNED
    attempts: int = 0
    artifact_digest: str | None = None
    skip_reason: str | None = None
    repair_of: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal_requirement": self.goal_requirement,
            "action": self.action,
            "expected_artifact": self.expected_artifact,
            "evidence_required": list(self.evidence_required),
            "pass_condition": self.pass_condition.to_dict(),
            "failure_condition": self.failure_condition,
            "dependencies": list(self.dependencies),
            "allowed_tools": list(self.allowed_tools),
            "max_attempts": self.max_attempts,
            "status": self.status.value,
            "attempts": self.attempts,
            "artifact_digest": self.artifact_digest,
            "skip_reason": self.skip_reason,
            "repair_of": self.repair_of,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            task_id=str(data["task_id"]),
            goal_requirement=str(data["goal_requirement"]),
            action=str(data["action"]),
            expected_artifact=str(data["expected_artifact"]),
            evidence_required=list(data.get("evidence_required", [])),
            pass_condition=PassCondition.from_dict(dict(data["pass_condition"])),
            failure_condition=str(data.get("failure_condition", "")),
            dependencies=list(data.get("dependencies", [])),
            allowed_tools=list(data.get("allowed_tools", [])),
            max_attempts=int(data.get("max_attempts", 3)),
            status=TaskStatus(data.get("status", "PLANNED")),
            attempts=int(data.get("attempts", 0)),
            artifact_digest=data.get("artifact_digest"),
            skip_reason=data.get("skip_reason"),
            repair_of=data.get("repair_of"),
        )


@dataclass
class RunState:
    """Persisted run state; written via atomic replacement after every significant action."""

    goal_id: str
    run_id: str
    contract_digest: str
    status: RunStatus
    created_at: str
    updated_at: str
    current_task_id: str | None = None
    iterations: int = 0
    human_interventions: int = 0
    human_active_minutes: float = 0.0
    budget_spent: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    unblock_requirement: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "run_id": self.run_id,
            "contract_digest": self.contract_digest,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_task_id": self.current_task_id,
            "iterations": self.iterations,
            "human_interventions": self.human_interventions,
            "human_active_minutes": self.human_active_minutes,
            "budget_spent": dict(self.budget_spent),
            "flags": list(self.flags),
            "blocked_reason": self.blocked_reason,
            "unblock_requirement": self.unblock_requirement,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        return cls(
            goal_id=str(data["goal_id"]),
            run_id=str(data["run_id"]),
            contract_digest=str(data["contract_digest"]),
            status=RunStatus(data["status"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            current_task_id=data.get("current_task_id"),
            iterations=int(data.get("iterations", 0)),
            human_interventions=int(data.get("human_interventions", 0)),
            human_active_minutes=float(data.get("human_active_minutes", 0.0)),
            budget_spent={k: float(v) for k, v in dict(data.get("budget_spent", {})).items()},
            flags=list(data.get("flags", [])),
            blocked_reason=data.get("blocked_reason"),
            unblock_requirement=data.get("unblock_requirement"),
        )


def utc_now() -> str:
    """ISO-8601 UTC timestamp used across all persisted records."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
