"""Budgets, duplicate-action detection, and circuit breakers with blocking reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from loop_engineering.domain.errors import BudgetExhausted, CircuitOpen
from loop_engineering.domain.models import PassCondition, Task
from loop_engineering.runtime.budget import Budget
from loop_engineering.runtime.circuit_breaker import CircuitBreaker
from loop_engineering.runtime.duplicate_detection import ActionRegistry


def test_budget_exhaustion() -> None:
    budget = Budget(max_iterations=2)
    budget.charge(iterations=1)
    budget.charge(iterations=1)
    with pytest.raises(BudgetExhausted, match="iteration budget"):
        budget.charge(iterations=1)


def test_duplicate_action_detection() -> None:
    reg = ActionRegistry()
    reg.record("fetch", {"page": 1}, evidence_digest="d1")
    assert not reg.is_repeat_without_new_evidence("fetch", {"page": 1})
    reg.record("fetch", {"page": 1}, evidence_digest="d1")
    assert reg.is_repeat_without_new_evidence("fetch", {"page": 1})
    # new evidence resets the condition
    reg.record("fetch", {"page": 1}, evidence_digest="d2")
    assert not reg.is_repeat_without_new_evidence("fetch", {"page": 1})
    # different params are a different action
    assert not reg.is_repeat_without_new_evidence("fetch", {"page": 2})


def _breaker(tmp_path: Path) -> CircuitBreaker:
    return CircuitBreaker(tmp_path)


def _assert_blocked(tmp_path: Path, needle: str) -> None:
    report = tmp_path / "reports" / "BLOCKED.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Exact unblock requirement" in text
    assert needle in text


def test_repeated_failure_trips_breaker(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_failure("t1: artifact missing")
    with pytest.raises(CircuitOpen) as exc:
        breaker.record_failure("t1: artifact missing")
    assert exc.value.unblock_requirement
    _assert_blocked(tmp_path, "same failure repeated")


def test_duplicate_action_trips_breaker(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_action("scan", {}, "same-digest")
    breaker.record_action("scan", {}, "same-digest")
    with pytest.raises(CircuitOpen):
        breaker.check_duplicate_action("scan", {})
    _assert_blocked(tmp_path, "without new evidence")


def test_no_progress_trips_breaker(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    breaker.record_iteration("mark-a")
    breaker.record_iteration("mark-a")
    breaker.record_iteration("mark-a")
    with pytest.raises(CircuitOpen, match="no measurable progress"):
        breaker.record_iteration("mark-a")
    _assert_blocked(tmp_path, "no measurable progress")


def test_max_attempts_trips_breaker(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    task = Task(
        task_id="t1",
        goal_requirement="req",
        action="act",
        expected_artifact="a.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="fc",
        max_attempts=2,
        attempts=2,
    )
    with pytest.raises(CircuitOpen, match="max attempts"):
        breaker.check_task_attempts(task)
    _assert_blocked(tmp_path, "human decision required")


def test_identity_and_source_breakers(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    with pytest.raises(CircuitOpen, match="identity"):
        breaker.identity_unresolved("subject-x", "two candidates match")
    _assert_blocked(tmp_path, "two corroborating public profile attributes")
    with pytest.raises(CircuitOpen, match="inaccessible"):
        breaker.source_inaccessible("https://example.com/profile")


def test_forbidden_action_breaker(tmp_path: Path) -> None:
    breaker = _breaker(tmp_path)
    with pytest.raises(CircuitOpen, match="forbidden"):
        breaker.forbidden_action("delete remote branch")
    _assert_blocked(tmp_path, "contract amendment")
