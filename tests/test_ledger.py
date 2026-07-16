"""Append-only JSONL ledgers: the audit trail a run is reconstructed from."""

from __future__ import annotations

from pathlib import Path

from loop_engineering.runtime.ledger import RunLedger, append_jsonl, read_jsonl


def test_append_jsonl_is_append_only(tmp_path: Path) -> None:
    target = tmp_path / "log.jsonl"
    append_jsonl(target, {"n": 1})
    append_jsonl(target, {"n": 2})
    assert read_jsonl(target) == [{"n": 1}, {"n": 2}]
    # appending never rewrites earlier lines
    first_line = target.read_text(encoding="utf-8").splitlines()[0]
    append_jsonl(target, {"n": 3})
    assert target.read_text(encoding="utf-8").splitlines()[0] == first_line
    assert len(read_jsonl(target)) == 3


def test_read_jsonl_missing_file_and_blank_lines(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "absent.jsonl") == []
    target = tmp_path / "log.jsonl"
    target.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    assert read_jsonl(target) == [{"a": 1}, {"b": 2}]


def test_run_ledger_transitions_and_events(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.record_transition("t1", "PLANNED", "READY", detail="deps verified", actor="runtime")
    ledger.record_transition("t1", "READY", "RUNNING", actor="executor")
    ledger.record_event("planned", {"task_count": 2})

    transitions = ledger.transitions()
    assert [t["to"] for t in transitions] == ["READY", "RUNNING"]
    assert transitions[0]["task_id"] == "t1" and transitions[0]["actor"] == "runtime"
    assert all("ts" in t for t in transitions)

    events = ledger.events()
    assert events[0]["kind"] == "planned"
    assert events[0]["detail"] == {"task_count": 2}
