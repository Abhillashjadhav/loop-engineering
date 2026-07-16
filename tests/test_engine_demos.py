"""Engine-level demos: full synthetic E2E, interrupted-run resume, six-run
stability, automatic repair below 70, planted failures, identity blocking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.conftest import GITHUB_FIXTURES, DemoUseCase, NeverPassesUseCase, make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import CircuitOpen
from loop_engineering.domain.models import RunStatus, TaskStatus
from loop_engineering.runtime.engine import Engine, SimulatedInterruption
from loop_engineering.runtime.ledger import read_jsonl
from loop_engineering.use_cases.github_authority_audit.datasource import FixtureDataSource
from loop_engineering.use_cases.github_authority_audit.runner import AuditUseCase


def audit_engine(tmp_path: Path, contract, subjects) -> Engine:  # type: ignore[no-untyped-def]
    return Engine(
        contract,
        AuditUseCase(FixtureDataSource(GITHUB_FIXTURES), subjects),
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )


def test_full_synthetic_e2e_demo(tmp_path: Path, audit_contract, audit_subjects) -> None:  # type: ignore[no-untyped-def]
    engine = audit_engine(tmp_path, audit_contract, audit_subjects)
    result = engine.run()
    assert result.state.status == RunStatus.COMPLETE
    assert result.gate_a is not None and result.gate_a.verdict.value == "COMPLETE"
    assert result.gate_b is not None and result.gate_b.score >= 80
    assert result.delivered

    # loop 2 ran at every stage boundary plus the final all-tasks pass
    loop2_stages = {v.subject_id for v in result.verifications if v.loop == "loop2_drift"}
    assert {"builder", "templater", "z", "all-tasks"} <= loop2_stages

    # six-run stability ran and preserved the planted disagreement
    stability = json.loads((engine.run_directory / "verifications" / "stability.json").read_text())
    assert stability["variant_count"] == 6
    assert "templater/prompt-pack-07:primary" in stability["unstable"]
    per_variant = stability["unstable"]["templater/prompt-pack-07:primary"]
    assert per_variant["skeptical"] == "LIKELY_SHALLOW_OR_TEMPLATED"
    assert per_variant["standard"] == "AI_ASSISTED_BUT_MEANINGFUL"

    # the two planted slop repos were detected with counter-evidence recorded
    scorecards = result.pack_dir / "repository-scorecards"  # type: ignore[operator]
    wrapper = json.loads((scorecards / "templater--gpt-wrapper-01.json").read_text())
    assert wrapper["classification"]["primary"] == "LIKELY_SHALLOW_OR_TEMPLATED"
    assert wrapper["classification"]["counter_evidence"]["strongest_counter_evidence"]
    builder = json.loads((scorecards / "builder--agent-orchestrator.json").read_text())
    assert builder["classification"]["primary"] == "SUBSTANTIVE_TECHNICAL_BUILD"


def test_interrupted_run_resumes_without_skipping(  # type: ignore[no-untyped-def]
    tmp_path: Path, audit_contract, audit_subjects
) -> None:
    engine = audit_engine(tmp_path, audit_contract, audit_subjects)
    with pytest.raises(SimulatedInterruption):
        engine.run(interrupt_after=3)
    assert engine.state.status == RunStatus.INTERRUPTED
    run_directory = engine.run_directory

    resumed = Engine.resume(
        run_directory,
        AuditUseCase(FixtureDataSource(GITHUB_FIXTURES), audit_subjects),
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    result = resumed.run()
    assert result.state.status == RunStatus.COMPLETE
    assert result.delivered

    # no task was skipped: every planned task is VERIFIED in the final queue
    assert resumed.queue is not None
    statuses = {t.task_id: t.status for t in resumed.queue.all_tasks()}
    assert all(s == TaskStatus.VERIFIED for s in statuses.values()), statuses
    # the interrupted (EXECUTED-but-unverified) task was reset and redone
    events = read_jsonl(run_directory / "events.jsonl")
    resumed_events = [e for e in events if e["kind"] == "resumed"]
    assert resumed_events and resumed_events[0]["detail"]["reset_tasks"]


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


def test_identity_ambiguity_blocks_audit(tmp_path: Path, audit_contract) -> None:  # type: ignore[no-untyped-def]
    subjects = [
        {
            "slug": "ambiguous",
            "display_name": "Alex Doe",
            "candidate_login": "ambiguous-a",
            "expected_attributes": {"name": "Alex Doe", "company": "Globex"},
        }
    ]
    engine = audit_engine(tmp_path, audit_contract, subjects)
    with pytest.raises(CircuitOpen):
        engine.run()
    assert engine.state.status == RunStatus.BLOCKED
    report = (engine.run_directory / "reports" / "BLOCKED.md").read_text(encoding="utf-8")
    assert "collides" in report or "failure repeated" in report


def test_contract_digest_checked_at_engine_start(tmp_path: Path, audit_subjects) -> None:  # type: ignore[no-untyped-def]
    from loop_engineering.domain.errors import ContractViolation

    contract = goal_contract.lock(make_contract_draft())
    contract["goal_statement"] = "tampered"
    with pytest.raises(ContractViolation):
        Engine(
            contract,
            AuditUseCase(FixtureDataSource(GITHUB_FIXTURES), audit_subjects),
            runs_root=tmp_path / "runs",
        )
