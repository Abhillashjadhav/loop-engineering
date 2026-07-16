"""Atomic task transitions, one-at-a-time sequencing, failed-verification gate."""

from __future__ import annotations

import pytest

from loop_engineering.domain.errors import InvalidTransition, SequencingViolation
from loop_engineering.domain.models import PassCondition, Task, TaskStatus
from loop_engineering.runtime.task_queue import TaskQueue


def make_task(task_id: str, deps: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement="req",
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
        dependencies=deps or [],
    )


def test_legal_lifecycle() -> None:
    q = TaskQueue([make_task("a")])
    t = q.next_task()
    assert t is not None and t.status == TaskStatus.READY
    q.transition("a", TaskStatus.RUNNING)
    assert q.get("a").attempts == 1
    q.transition("a", TaskStatus.EXECUTED)
    q.transition("a", TaskStatus.VERIFIED)
    assert q.complete()


def test_illegal_transitions_raise() -> None:
    q = TaskQueue([make_task("a")])
    with pytest.raises(InvalidTransition):
        q.transition("a", TaskStatus.VERIFIED)  # PLANNED -> VERIFIED
    q.refresh_ready()
    q.transition("a", TaskStatus.RUNNING)
    with pytest.raises(InvalidTransition):
        q.transition("a", TaskStatus.VERIFIED)  # RUNNING -> VERIFIED skips EXECUTED
    with pytest.raises(InvalidTransition):
        q.transition("a", TaskStatus.PLANNED)


def test_skip_requires_reason() -> None:
    q = TaskQueue([make_task("a")])
    with pytest.raises(InvalidTransition, match="requires a reason"):
        q.transition("a", TaskStatus.SKIPPED_WITH_REASON)
    q.transition("a", TaskStatus.SKIPPED_WITH_REASON, detail="superseded by t-b")
    assert q.get("a").skip_reason == "superseded by t-b"


def test_one_task_at_a_time() -> None:
    q = TaskQueue([make_task("a"), make_task("b")])
    t = q.next_task()
    assert t is not None
    q.transition(t.task_id, TaskStatus.RUNNING)
    with pytest.raises(SequencingViolation, match="in flight"):
        q.next_task()


def test_cannot_proceed_after_failed_verification() -> None:
    q = TaskQueue([make_task("a"), make_task("b")])
    t = q.next_task()
    assert t is not None
    q.transition("a", TaskStatus.RUNNING)
    q.transition("a", TaskStatus.EXECUTED)
    q.transition("a", TaskStatus.FAILED, detail="verification failed")
    with pytest.raises(SequencingViolation, match="unresolved failed"):
        q.next_task()


def test_dependencies_gate_readiness() -> None:
    q = TaskQueue([make_task("a"), make_task("b", deps=["a"])])
    t = q.next_task()
    assert t is not None and t.task_id == "a"
    q.transition("a", TaskStatus.RUNNING)
    q.transition("a", TaskStatus.EXECUTED)
    q.transition("a", TaskStatus.VERIFIED)
    t2 = q.next_task()
    assert t2 is not None and t2.task_id == "b"


def test_add_task_requires_known_dependencies() -> None:
    q = TaskQueue([make_task("a")])
    with pytest.raises(InvalidTransition, match="unknown tasks"):
        q.add_task(make_task("r", deps=["ghost"]), reason="repair")


def test_only_verified_satisfies_completion() -> None:
    q = TaskQueue([make_task("a")])
    q.refresh_ready()
    q.transition("a", TaskStatus.RUNNING)
    q.transition("a", TaskStatus.EXECUTED)
    assert not q.complete()
    q.transition("a", TaskStatus.VERIFIED)
    assert q.complete()
