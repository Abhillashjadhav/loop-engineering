"""Recovery Controller (spec §6 Loop 1 routing, §7 auto-repair, §8 breakers).

Failure routing:
- a failed task retries via REPAIRING -> READY while attempts remain;
- attempts exhausted trips the circuit breaker (blocking report, CircuitOpen);
- a Gate B score below 70 creates explicit repair tasks — plan growth is
  recorded, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loop_engineering.domain.models import PassCondition, Task, TaskStatus, utc_now
from loop_engineering.planning.planner import PlanChange
from loop_engineering.runtime.circuit_breaker import CircuitBreaker
from loop_engineering.runtime.ledger import RunLedger
from loop_engineering.runtime.task_queue import TaskQueue


@dataclass
class RepairOutcome:
    task_id: str
    action: str  # "requeued" | "repair_task_created"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "action": self.action, "detail": self.detail}


class RecoveryController:
    def __init__(
        self, queue: TaskQueue, breaker: CircuitBreaker, ledger: RunLedger | None = None
    ) -> None:
        self.queue = queue
        self.breaker = breaker
        self.ledger = ledger
        self._repair_counter = 0
        self.plan_changes: list[PlanChange] = []

    def handle_task_failure(self, task: Task, failure_reason: str) -> RepairOutcome:
        """Route one failed task. Trips the breaker on repeats/attempt limits."""
        self.breaker.record_failure(f"{task.task_id}:{failure_reason}")
        self.breaker.check_task_attempts(task)
        self.queue.transition(
            task.task_id, TaskStatus.REPAIRING, detail=failure_reason, actor="recovery"
        )
        self.queue.transition(
            task.task_id,
            TaskStatus.READY,
            detail=f"requeued (attempt {task.attempts}/{task.max_attempts})",
            actor="recovery",
        )
        if self.ledger:
            self.ledger.record_event(
                "task_requeued", {"task_id": task.task_id, "reason": failure_reason}
            )
        return RepairOutcome(task.task_id, "requeued", failure_reason)

    def create_repair_task_from(self, task: Task) -> Task:
        """Register a use-case-built repair task: recorded plan growth, never silent."""
        if task.repair_of is None:
            task.repair_of = "e2e_review"
        self.queue.add_task(task, reason=f"auto-repair: {task.action}")
        self.plan_changes.append(
            PlanChange(
                changed_at=utc_now(),
                reason=f"automatic repair: {task.action}",
                evidence=f"end-to-end review requested repair of {task.repair_of}",
                added_task_ids=[task.task_id],
            )
        )
        if self.ledger:
            self.ledger.record_event(
                "repair_task_created", {"task_id": task.task_id, "action": task.action}
            )
        return task

    def create_repair_task(
        self,
        deficient_subject: str,
        gap: str,
        goal_requirement: str,
        expected_artifact: str,
        pass_condition: PassCondition,
        evidence_required: list[str] | None = None,
    ) -> Task:
        """Create an explicit repair task for a Gate B gap (score < 70)."""
        self._repair_counter += 1
        task = Task(
            task_id=f"repair-{self._repair_counter:03d}",
            goal_requirement=goal_requirement,
            action=f"Repair gap in {deficient_subject}: {gap}",
            expected_artifact=expected_artifact,
            evidence_required=list(evidence_required or []),
            pass_condition=pass_condition,
            failure_condition=f"gap persists: {gap}",
            repair_of=deficient_subject,
            status=TaskStatus.PLANNED,
        )
        self.queue.add_task(task, reason=f"e2e review gap: {gap}")
        self.plan_changes.append(
            PlanChange(
                changed_at=utc_now(),
                reason=f"automatic repair: {gap}",
                evidence=f"end-to-end review found {deficient_subject} below threshold",
                added_task_ids=[task.task_id],
            )
        )
        if self.ledger:
            self.ledger.record_event("repair_task_created", {"task_id": task.task_id, "gap": gap})
        return task
