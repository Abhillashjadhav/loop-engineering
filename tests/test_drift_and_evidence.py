"""Loop 2 goal-drift math (Loop 3 evidence rules join in a later PR)."""

from __future__ import annotations

from typing import Any

from tests.conftest import make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.models import PassCondition, Task
from loop_engineering.planning.planner import coverage
from loop_engineering.verification import loop2_drift


def make_task(task_id: str, requirement: str) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement=requirement,
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
    )


def contract_with_scope(scope: list[str]) -> dict[str, Any]:
    return goal_contract.lock(make_contract_draft(scope=scope))


def test_drift_zero_when_aligned() -> None:
    contract = contract_with_scope(["r1", "r2"])
    tasks = [make_task("a", "r1"), make_task("b", "r2")]
    report = coverage(contract, tasks)
    assert report.drift_pct == 0.0
    result = loop2_drift.verify_plan(contract, tasks)
    assert result.passed


def test_orphan_task_is_drift() -> None:
    contract = contract_with_scope(["r1"])
    tasks = [make_task("a", "r1"), make_task("b", "sneaky new feature")]
    report = coverage(contract, tasks)
    assert report.orphan_task_ids == ["b"]
    assert report.drift_pct > 5.0
    assert not loop2_drift.verify_plan(contract, tasks).passed


def test_uncovered_requirement_is_drift() -> None:
    contract = contract_with_scope(["r1", "r2", "r3"])
    tasks = [make_task("a", "r1"), make_task("b", "r2")]
    report = coverage(contract, tasks)
    assert report.uncovered_requirements == ["r3"]
    assert not loop2_drift.verify_plan(contract, tasks).passed


def test_drift_calculation_value() -> None:
    # 1 orphan + 1 uncovered over (2 tasks + 2 requirements) = 50%
    contract = contract_with_scope(["r1", "r2"])
    tasks = [make_task("a", "r1"), make_task("b", "orphan-req")]
    assert coverage(contract, tasks).drift_pct == 50.0
