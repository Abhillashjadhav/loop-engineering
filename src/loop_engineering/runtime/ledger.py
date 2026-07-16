"""Append-only JSONL ledgers: task transitions and run events.

The ledger is the audit trail — a run must be reconstructable from it alone.
Nothing is ever rewritten; corrections are new entries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loop_engineering.domain.models import utc_now

TASK_LEDGER = "task-ledger.jsonl"
EVENTS_LOG = "events.jsonl"


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=False, ensure_ascii=True) + "\n")
        fh.flush()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                loaded = json.loads(line)
                if isinstance(loaded, dict):
                    records.append(loaded)
    return records


class RunLedger:
    """Task-transition + event ledgers for one run directory."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @property
    def task_ledger_path(self) -> Path:
        return self.directory / TASK_LEDGER

    @property
    def events_path(self) -> Path:
        return self.directory / EVENTS_LOG

    def record_transition(
        self,
        task_id: str,
        from_status: str,
        to_status: str,
        detail: str = "",
        actor: str = "runtime",
    ) -> None:
        append_jsonl(
            self.task_ledger_path,
            {
                "ts": utc_now(),
                "task_id": task_id,
                "from": from_status,
                "to": to_status,
                "actor": actor,
                "detail": detail,
            },
        )

    def record_event(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        append_jsonl(self.events_path, {"ts": utc_now(), "kind": kind, "detail": detail or {}})

    def transitions(self) -> list[dict[str, Any]]:
        return read_jsonl(self.task_ledger_path)

    def events(self) -> list[dict[str, Any]]:
        return read_jsonl(self.events_path)
