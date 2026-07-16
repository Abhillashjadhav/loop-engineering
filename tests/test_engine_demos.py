"""Engine-level demos: automatic repair below 70, planted failures, safe stops.

The full-scale synthetic audit E2E, interrupted-run resume, and six-run
stability demos join when the audit use case lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import DemoUseCase, NeverPassesUseCase, make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import CircuitOpen
from loop_engineering.domain.models import RunStatus, TaskStatus
from loop_engineering.runtime.engine import Engine
from loop_engineering.runtime.ledger import read_jsonl


def test_auto_repair_below_70_then_delivers(tmp_path: Path) -> None:
    contract = goal_contract.lock(make_contract_draft())
    engine = Engine(
        contract,
        DemoUseCase(),
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    result = engine.run()
    # first review was below 70 -> repair tasks created -> final result delivered
    events = read_jsonl(engine.run_directory / "events.jsonl")
    assert any(e["kind"] == "auto_repair_round" for e in events)
    assert result.gate_b is not None and result.gate_b.score >= 70
    assert result.delivered
    assert engine.queue is not None
    repair_tasks = [t for t in engine.queue.all_tasks() if t.task_id.startswith("repair-")]
    assert repair_tasks and all(t.status == TaskStatus.VERIFIED for t in repair_tasks)


def test_planted_failure_detected_then_recovered(tmp_path: Path) -> None:
    contract = goal_contract.lock(make_contract_draft())
    engine = Engine(
        contract,
        DemoUseCase(fail_first_attempt=True),
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    result = engine.run()
    assert result.delivered
    ledger = read_jsonl(engine.run_directory / "task-ledger.jsonl")
    failures = [e for e in ledger if e["to"] == "FAILED"]
    assert failures, "the planted first-attempt failure must be recorded"
    requeues = [e for e in ledger if e["to"] == "REPAIRING"]
    assert requeues


def test_persistent_failure_stops_safely_with_blocking_report(tmp_path: Path) -> None:
    contract = goal_contract.lock(make_contract_draft())
    engine = Engine(
        contract,
        NeverPassesUseCase(),
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    with pytest.raises(CircuitOpen):
        engine.run()
    report = engine.run_directory / "reports" / "BLOCKED.md"
    assert report.is_file()
    assert "Exact unblock requirement" in report.read_text(encoding="utf-8")
    assert engine.state.status == RunStatus.BLOCKED
