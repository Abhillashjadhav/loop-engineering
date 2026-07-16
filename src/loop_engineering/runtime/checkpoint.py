"""Checkpoints and crash-safe resume.

A checkpoint snapshots run state + full task list. On restart, the run resumes
from the first task that is not both EXECUTED and VERIFIED — i.e. every task
that has not reached VERIFIED is re-queued for (re-)execution or
(re-)verification, and no VERIFIED work is repeated or skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loop_engineering.domain.models import RunState, Task, TaskStatus, utc_now
from loop_engineering.runtime.state import atomic_write_json, read_json


def write_checkpoint(
    run_directory: str | Path, state: RunState, tasks: list[Task], label: str
) -> Path:
    directory = Path(run_directory) / "checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    seq = len(list(directory.glob("checkpoint-*.json"))) + 1
    path = directory / f"checkpoint-{seq:05d}.json"
    atomic_write_json(
        path,
        {
            "label": label,
            "written_at": utc_now(),
            "state": state.to_dict(),
            "tasks": [t.to_dict() for t in tasks],
        },
    )
    return path


def latest_checkpoint(run_directory: str | Path) -> dict[str, Any] | None:
    directory = Path(run_directory) / "checkpoints"
    if not directory.exists():
        return None
    files = sorted(directory.glob("checkpoint-*.json"))
    if not files:
        return None
    loaded = read_json(files[-1])
    return loaded if isinstance(loaded, dict) else None


def load_tasks_from_checkpoint(checkpoint: dict[str, Any]) -> list[Task]:
    return [Task.from_dict(d) for d in checkpoint.get("tasks", [])]


def normalize_for_resume(tasks: list[Task]) -> list[str]:
    """Reset in-flight statuses so the queue can lawfully re-run them.

    - RUNNING  -> READY  (execution was interrupted; redo it)
    - EXECUTED -> READY  (verification never confirmed it; redo it —
      an executor statement is not proof)

    Returns the ids of tasks needing attention on resume: those reset to
    READY plus FAILED tasks (left FAILED — recovery must resolve them
    explicitly; they are reported, not re-queued). VERIFIED and
    SKIPPED_WITH_REASON tasks are never touched, so no completed work is
    repeated and no task is skipped.
    """
    reset: list[str] = []
    for t in tasks:
        if t.status in (TaskStatus.RUNNING, TaskStatus.EXECUTED, TaskStatus.REPAIRING):
            t.status = TaskStatus.READY
            reset.append(t.task_id)
        elif t.status == TaskStatus.FAILED:
            # Failure survives restart; recovery must resolve it explicitly.
            reset.append(t.task_id)
    return reset


def resume_point(tasks: list[Task]) -> str | None:
    """First task (in id order) that has not reached a terminal accepted state."""
    for t in sorted(tasks, key=lambda t: t.task_id):
        if t.status not in (TaskStatus.VERIFIED, TaskStatus.SKIPPED_WITH_REASON):
            return t.task_id
    return None
