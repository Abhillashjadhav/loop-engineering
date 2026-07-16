"""Dependency-aware task queue enforcing the atomic-task state machine.

Guarantees (PD-04):
- exactly one task may run at a time;
- no next task is issued while any task is EXECUTED-but-unverified, RUNNING,
  or FAILED-and-unresolved;
- transitions outside ALLOWED_TRANSITIONS raise InvalidTransition.
"""

from __future__ import annotations

from loop_engineering.domain.errors import InvalidTransition, SequencingViolation
from loop_engineering.domain.models import ALLOWED_TRANSITIONS, Task, TaskStatus
from loop_engineering.runtime.ledger import RunLedger


class TaskQueue:
    def __init__(self, tasks: list[Task], ledger: RunLedger | None = None) -> None:
        self._tasks: dict[str, Task] = {t.task_id: t for t in tasks}
        if len(self._tasks) != len(tasks):
            raise InvalidTransition("duplicate task ids in queue")
        self._ledger = ledger

    # -- inspection ---------------------------------------------------------

    def get(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def all_tasks(self) -> list[Task]:
        return sorted(self._tasks.values(), key=lambda t: t.task_id)

    def by_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self.all_tasks() if t.status == status]

    def unresolved_failures(self) -> list[Task]:
        return self.by_status(TaskStatus.FAILED)

    def in_flight(self) -> list[Task]:
        return [
            t
            for t in self.all_tasks()
            if t.status in (TaskStatus.RUNNING, TaskStatus.EXECUTED, TaskStatus.REPAIRING)
        ]

    def complete(self) -> bool:
        """True when every task reached a terminal accepted state."""
        return all(
            t.status in (TaskStatus.VERIFIED, TaskStatus.SKIPPED_WITH_REASON)
            for t in self._tasks.values()
        )

    # -- scheduling ---------------------------------------------------------

    def _deps_verified(self, task: Task) -> bool:
        return all(self._tasks[d].status == TaskStatus.VERIFIED for d in task.dependencies)

    def refresh_ready(self) -> list[Task]:
        """Promote PLANNED tasks whose dependencies are all VERIFIED."""
        promoted: list[Task] = []
        for t in self.all_tasks():
            if t.status == TaskStatus.PLANNED and self._deps_verified(t):
                self.transition(t.task_id, TaskStatus.READY, detail="dependencies verified")
                promoted.append(t)
        return promoted

    def next_task(self) -> Task | None:
        """The single next READY task, or None when nothing is ready.

        Raises SequencingViolation if asked while a task is in flight or a
        failure is unresolved — the loop may never continue past a failed
        verification.
        """
        flying = self.in_flight()
        if flying:
            raise SequencingViolation(
                f"task(s) in flight: {[t.task_id for t in flying]}; "
                "one task at a time, verified before the next"
            )
        failed = self.unresolved_failures()
        if failed:
            raise SequencingViolation(
                f"unresolved failed task(s): {[t.task_id for t in failed]}; "
                "recovery must resolve failures before the next task"
            )
        self.refresh_ready()
        ready = self.by_status(TaskStatus.READY)
        return ready[0] if ready else None

    # -- transitions --------------------------------------------------------

    def transition(
        self, task_id: str, to_status: TaskStatus, detail: str = "", actor: str = "runtime"
    ) -> Task:
        task = self._tasks[task_id]
        allowed = ALLOWED_TRANSITIONS[task.status]
        if to_status not in allowed:
            raise InvalidTransition(
                f"task {task_id}: {task.status.value} -> {to_status.value} is not allowed "
                f"(allowed: {sorted(s.value for s in allowed)})"
            )
        if to_status == TaskStatus.SKIPPED_WITH_REASON and not detail.strip():
            raise InvalidTransition(f"task {task_id}: SKIPPED_WITH_REASON requires a reason")
        from_status = task.status
        task.status = to_status
        if to_status == TaskStatus.RUNNING:
            task.attempts += 1
        if to_status == TaskStatus.SKIPPED_WITH_REASON:
            task.skip_reason = detail
        if self._ledger is not None:
            self._ledger.record_transition(
                task_id, from_status.value, to_status.value, detail=detail, actor=actor
            )
        return task

    def add_task(self, task: Task, reason: str, actor: str = "recovery") -> None:
        """Add an explicit new task (plan growth is loud, never silent)."""
        if task.task_id in self._tasks:
            raise InvalidTransition(f"task {task.task_id} already exists")
        missing = [d for d in task.dependencies if d not in self._tasks]
        if missing:
            raise InvalidTransition(f"task {task.task_id} depends on unknown tasks {missing}")
        self._tasks[task.task_id] = task
        if self._ledger is not None:
            self._ledger.record_transition(
                task.task_id, "(none)", task.status.value, detail=f"added: {reason}", actor=actor
            )
