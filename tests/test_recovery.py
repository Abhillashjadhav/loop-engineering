"""Recovery controller: requeue within limits, explicit repair tasks, safe stops."""

from __future__ import annotations

from pathlib import Path

import pytest

from loop_engineering.domain.errors import CircuitOpen
from loop_engineering.domain.models import PassCondition, Task, TaskStatus
from loop_engineering.recovery.controller import RecoveryController
from loop_engineering.runtime.circuit_breaker import CircuitBreaker
from loop_engineering.runtime.ledger import RunLedger
from loop_engineering.runtime.task_queue import TaskQueue


def make_task(task_id: str) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement="req",
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
    )


def controller(tmp_path: Path, tasks: list[Task]) -> tuple[RecoveryController, TaskQueue]:
    ledger = RunLedger(tmp_path)
    queue = TaskQueue(tasks, ledger)
    return RecoveryController(queue, CircuitBreaker(tmp_path), ledger), queue


def fail_task(queue: TaskQueue, task_id: str, reason: str) -> Task:
    queue.refresh_ready()
    queue.transition(task_id, TaskStatus.RUNNING)
    queue.transition(task_id, TaskStatus.EXECUTED)
    return queue.transition(task_id, TaskStatus.FAILED, detail=reason)


def test_first_failure_requeues_through_repairing(tmp_path: Path) -> None:
    recovery, queue = controller(tmp_path, [make_task("t1")])
    task = fail_task(queue, "t1", "artifact missing")
    outcome = recovery.handle_task_failure(task, "artifact missing")
    assert outcome.action == "requeued"
    assert queue.get("t1").status == TaskStatus.READY
    transitions = [t["to"] for t in RunLedger(tmp_path).transitions()]
    assert "REPAIRING" in transitions and transitions[-1] == "READY"


def test_same_failure_twice_stops_safely_with_blocking_report(tmp_path: Path) -> None:
    recovery, queue = controller(tmp_path, [make_task("t1")])
    task = fail_task(queue, "t1", "artifact missing")
    recovery.handle_task_failure(task, "artifact missing")
    queue.transition("t1", TaskStatus.RUNNING)
    queue.transition("t1", TaskStatus.EXECUTED)
    task = queue.transition("t1", TaskStatus.FAILED, detail="artifact missing")
    with pytest.raises(CircuitOpen):
        recovery.handle_task_failure(task, "artifact missing")
    report = tmp_path / "reports" / "BLOCKED.md"
    assert report.is_file()
    assert "Exact unblock requirement" in report.read_text(encoding="utf-8")


def test_repair_task_created_with_recorded_plan_change(tmp_path: Path) -> None:
    recovery, queue = controller(tmp_path, [make_task("t1")])
    repair = recovery.create_repair_task(
        deficient_subject="t1",
        gap="output contract dimension below threshold",
        goal_requirement="req",
        expected_artifact="repair.json",
        pass_condition=PassCondition(type="json_valid"),
    )
    assert repair.repair_of == "t1"
    assert queue.get(repair.task_id).status == TaskStatus.PLANNED
    assert recovery.plan_changes and recovery.plan_changes[0].added_task_ids == [repair.task_id]
    assert recovery.plan_changes[0].reason and recovery.plan_changes[0].evidence


def test_prebuilt_repair_task_registration(tmp_path: Path) -> None:
    recovery, queue = controller(tmp_path, [make_task("t1")])
    prebuilt = make_task("repair-001")
    registered = recovery.create_repair_task_from(prebuilt)
    assert registered.repair_of == "e2e_review"
    assert queue.get("repair-001") is prebuilt
    assert any(e["kind"] == "repair_task_created" for e in RunLedger(tmp_path).events())
