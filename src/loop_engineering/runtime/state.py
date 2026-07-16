"""Atomic, crash-safe state persistence.

Every write goes to a temp file in the same directory followed by
``os.replace`` so a crash never leaves a half-written state file.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loop_engineering.domain.models import RunState, utc_now


def atomic_write_json(path: str | Path, data: dict[str, Any] | list[Any]) -> None:
    """Write JSON atomically (temp file + os.replace in the same directory)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=p.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, p)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def run_dir(root: str | Path, goal_id: str, run_id: str) -> Path:
    """runs/<goal-id>/<run-id>/ layout (spec §8), created on demand."""
    d = Path(root) / goal_id / run_id
    for sub in ("checkpoints", "artifacts", "evidence", "verifications", "reports"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def save_state(directory: str | Path, state: RunState) -> None:
    state.updated_at = utc_now()
    atomic_write_json(Path(directory) / "state.json", state.to_dict())


def load_state(directory: str | Path) -> RunState:
    raw = read_json(Path(directory) / "state.json")
    if not isinstance(raw, dict):
        raise ValueError(f"corrupt state.json in {directory}")
    return RunState.from_dict(raw)
