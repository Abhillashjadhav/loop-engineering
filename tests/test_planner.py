"""Plan validation, deterministic ordering, and goal-coverage math."""

from __future__ import annotations

import pytest
from tests.conftest import make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import ContractViolation
from loop_engineering.domain.models import PassCondition, Task
from loop_engineering.planning.planner import coverage, execution_order, validate_plan


def make_task(
    task_id: str, requirement: str = "produce the demo report", deps: list[str] | None = None
) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement=requirement,
        action=f"do {task_id}",
        expected_artifact=f"{task_id}.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="missing",
        dependencies=deps or [],
    )


def locked() -> dict[str, object]:
    return goal_contract.lock(make_contract_draft())


def test_validate_plan_accepts_well_formed_plan() -> None:
    validate_plan(locked(), [make_task("a"), make_task("b", deps=["a"])])


def test_duplicate_task_ids_rejected() -> None:
    with pytest.raises(ContractViolation, match="duplicate task ids"):
        validate_plan(locked(), [make_task("a"), make_task("a")])


def test_unknown_dependency_rejected() -> None:
    with pytest.raises(ContractViolation, match="unknown tasks"):
        validate_plan(locked(), [make_task("a", deps=["ghost"])])


def test_dependency_cycle_rejected() -> None:
    a = make_task("a", deps=["b"])
    b = make_task("b", deps=["a"])
    with pytest.raises(ContractViolation, match="cycle"):
        validate_plan(locked(), [a, b])


def test_execution_order_is_deterministic_and_dependency_first() -> None:
    tasks = [make_task("c", deps=["a", "b"]), make_task("b", deps=["a"]), make_task("a")]
    ordered = [t.task_id for t in execution_order(tasks)]
    assert ordered == ["a", "b", "c"]


def test_coverage_and_drift_math() -> None:
    contract = goal_contract.lock(make_contract_draft(scope=["r1", "r2"]))
    tasks = [make_task("a", "r1"), make_task("b", "not-in-scope")]
    report = coverage(contract, tasks)
    assert report.covered_requirements == ["r1"]
    assert report.uncovered_requirements == ["r2"]
    assert report.orphan_task_ids == ["b"]
    # 1 orphan + 1 uncovered over (2 tasks + 2 requirements) = 50%
    assert report.drift_pct == 50.0


def test_fully_aligned_plan_has_zero_drift() -> None:
    contract = goal_contract.lock(make_contract_draft(scope=["r1"]))
    report = coverage(contract, [make_task("a", "r1")])
    assert report.drift_pct == 0.0
    assert not report.orphan_task_ids and not report.uncovered_requirements
