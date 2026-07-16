"""Checkpoints, crash-safe state writes, and resume semantics."""

from __future__ import annotations

from pathlib import Path

from loop_engineering.domain.models import (
    PassCondition,
    RunState,
    RunStatus,
    Task,
    TaskStatus,
    utc_now,
)
from loop_engineering.runtime.checkpoint import (
    latest_checkpoint,
    load_tasks_from_checkpoint,
    normalize_for_resume,
    resume_point,
    write_checkpoint,
)
from loop_engineering.runtime.state import atomic_write_json, load_state, read_json, save_state


def make_task(task_id: str, status: TaskStatus) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement="req",
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
        status=status,
    )


def make_state() -> RunState:
    return RunState(
        goal_id="g",
        run_id="r",
        contract_digest="sha256:00",
        status=RunStatus.RUNNING,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def test_atomic_write_and_read(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.json"
    atomic_write_json(target, {"k": 1})
    assert read_json(target) == {"k": 1}
    # no temp litter left behind
    leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_state_roundtrip(tmp_path: Path) -> None:
    state = make_state()
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded.run_id == "r" and loaded.status == RunStatus.RUNNING


def test_checkpoint_sequence_and_latest(tmp_path: Path) -> None:
    state = make_state()
    tasks = [make_task("a", TaskStatus.VERIFIED)]
    write_checkpoint(tmp_path, state, tasks, "one")
    write_checkpoint(tmp_path, state, tasks, "two")
    checkpoint = latest_checkpoint(tmp_path)
    assert checkpoint is not None and checkpoint["label"] == "two"
    assert load_tasks_from_checkpoint(checkpoint)[0].task_id == "a"


def test_resume_resets_inflight_but_never_verified_work() -> None:
    tasks = [
        make_task("a", TaskStatus.VERIFIED),
        make_task("b", TaskStatus.EXECUTED),  # executed but never verified: must redo
        make_task("c", TaskStatus.RUNNING),  # crashed mid-run: must redo
        make_task("d", TaskStatus.PLANNED),
    ]
    reset = normalize_for_resume(tasks)
    assert set(reset) == {"b", "c"}
    assert tasks[0].status == TaskStatus.VERIFIED  # verified work untouched
    assert tasks[1].status == TaskStatus.READY
    assert tasks[2].status == TaskStatus.READY
    assert tasks[3].status == TaskStatus.PLANNED
    assert resume_point(tasks) == "b"


def test_resume_reports_failed_tasks_without_requeueing_them() -> None:
    tasks = [make_task("a", TaskStatus.FAILED), make_task("b", TaskStatus.EXECUTED)]
    reset = normalize_for_resume(tasks)
    assert set(reset) == {"a", "b"}  # FAILED is reported for attention...
    assert tasks[0].status == TaskStatus.FAILED  # ...but never silently re-queued
    assert tasks[1].status == TaskStatus.READY


def test_resume_point_none_when_all_terminal() -> None:
    tasks = [make_task("a", TaskStatus.VERIFIED)]
    tasks[0].status = TaskStatus.VERIFIED
    assert resume_point(tasks) is None
