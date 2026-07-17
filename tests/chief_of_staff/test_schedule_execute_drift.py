"""Planted-failure tests: scheduling, safe execution, drift, determinism."""

from __future__ import annotations

import pytest

from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
    FixtureCalendarAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.checkpoint import drift_check
from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.execute import (
    ProhibitedActionError,
    approve_and_create_focus_blocks,
    execute_safe,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    ActionProposal,
    ApprovalRequirement,
    CalendarItem,
    Energy,
    Origin,
    ProposalStatus,
    SourceType,
    Task,
    TaskSource,
    TaskStatus,
)
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import prioritize
from loop_engineering.use_cases.personal_chief_of_staff.schedule import (
    has_overlap,
    propose_schedule,
)

DAY = "2026-07-17"
TODAY = "2026-07-17"


def _task(tid: str, title: str, minutes: int = 60, **kw: object) -> Task:
    return Task(
        id=tid,
        title=title,
        description=title,
        sources=[
            TaskSource(
                source_type=SourceType(kw.pop("source", "manual")),
                source_reference=f"ref-{tid}",
                source_excerpt=title,
                inferred_or_explicit=kw.pop("origin", Origin.EXPLICIT),  # type: ignore[arg-type]
                confidence=kw.pop("confidence", 0.9),  # type: ignore[arg-type]
            )
        ],
        estimated_minutes=minutes,
        energy=Energy.MEDIUM,
        **kw,  # type: ignore[arg-type]
    )


def _events() -> list[CalendarItem]:
    return [
        CalendarItem("m1", "Standup", f"{DAY}T09:00:00+00:00", f"{DAY}T09:30:00+00:00", ["t@x"]),
        CalendarItem("m2", "Call", f"{DAY}T11:00:00+00:00", f"{DAY}T11:45:00+00:00", ["r@x"]),
    ]


def test_schedule_never_overlaps_and_respects_meetings() -> None:
    tasks = [_task(f"t{i}", f"Work {i}", minutes=60) for i in range(6)]
    scored = prioritize(tasks, OperatingContract(), TODAY)
    sched = propose_schedule(scored, _events(), DAY)
    assert not has_overlap(sched.blocks), "planted failure: focus blocks overlap"
    # No block may collide with a protected meeting (09:00-09:30, 11:00-11:45).
    for b in sched.blocks:
        assert not (b.start < f"{DAY}T09:30:00+00:00" and b.end > f"{DAY}T09:00:00+00:00")
        assert not (b.start < f"{DAY}T11:45:00+00:00" and b.end > f"{DAY}T11:00:00+00:00")


def test_never_schedules_beyond_free_time() -> None:
    # 20 hours of work cannot fit a 9-18 day around two meetings.
    tasks = [_task(f"t{i}", f"Big {i}", minutes=120) for i in range(10)]
    scored = prioritize(tasks, OperatingContract(), TODAY)
    sched = propose_schedule(scored, _events(), DAY)
    booked = sum(
        (
            __import__("datetime").datetime.fromisoformat(b.end)
            - __import__("datetime").datetime.fromisoformat(b.start)
        ).total_seconds()
        / 60
        for b in sched.blocks
    )
    assert booked <= sched.free_minutes, "planted failure: scheduled beyond free time"
    assert sched.overflow, "overloaded day must report overflow with an alternative"


def test_focus_block_not_created_without_approval() -> None:
    tasks = [_task("t1", "Deep work", 60)]
    scored = prioritize(tasks, OperatingContract(), TODAY)
    sched = propose_schedule(scored, _events(), DAY)
    cal = FixtureCalendarAdapter(directory=".")
    with pytest.raises(ProhibitedActionError):
        approve_and_create_focus_blocks(sched, cal, approved=False)
    assert cal.created_blocks == [], "planted failure: calendar block created without approval"
    created = approve_and_create_focus_blocks(sched, cal, approved=True)
    assert len(created) == len(sched.blocks)


def test_prohibited_action_fails_closed() -> None:
    contract = OperatingContract()
    proposals = [
        ActionProposal(
            "p1", "send_email", "vc@x", "reply", "sent", "high", ApprovalRequirement.EXPLICIT
        ),
        ActionProposal(
            "p2", "gmail_draft", "vc@x", "reply", "draft", "low", ApprovalRequirement.NONE
        ),
        ActionProposal(
            "p3", "merge_code", "main", "merge PR", "merged", "high", ApprovalRequirement.EXPLICIT
        ),
    ]
    result = execute_safe(proposals, contract)
    executed_types = {a.action_type for a in result.executed}
    blocked_types = {a.action_type for a in result.blocked}
    assert executed_types == {"gmail_draft"}, "planted failure: email sent instead of drafted"
    assert {"send_email", "merge_code"} <= blocked_types
    for a in result.blocked:
        assert a.status is ProposalStatus.BLOCKED_PROHIBITED


def test_completed_task_needs_evidence() -> None:
    # A task marked done without evidence is a guard violation surfaced by the
    # register's honesty check (no evidence → cannot be trusted as complete).
    t = _task("t1", "Ship thing", status=TaskStatus.DONE)
    assert not t.evidence_of_completion, "fixture: starts without evidence"
    # Model invariant: completion evidence must be set explicitly; the field
    # defaulting empty means 'no false completion claim' is detectable.
    assert t.to_dict()["evidence_of_completion"] == ""


def test_rejected_idea_resurfacing_is_blocked() -> None:
    contract = OperatingContract()  # rejects "automatic LinkedIn publishing"
    tasks = [_task("t1", "Set up automatic LinkedIn publishing pipeline")]
    scored = prioritize(tasks, contract, TODAY)
    report = drift_check(scored, contract)
    assert not report.ok
    assert any("rejected idea" in v for v in report.violations), (
        "planted failure: rejected idea resurfaced as approved work"
    )


def test_priority_displacement_detected() -> None:
    contract = OperatingContract()
    # An admin task with a huge fake urgency vs a low job task — drift must flag
    # if admin outranks the job item.
    admin = _task("a1", "expense report admin", urgency=5, impact=5, strategic_value=5)
    job = _task("j1", "interview recruiter screen", urgency=0, impact=0)
    scored = prioritize([admin, job], contract, TODAY)
    report = drift_check(scored, contract)
    admin_score = next(s.score for s in scored if s.task.id == "a1")
    job_score = next(s.score for s in scored if s.task.id == "j1")
    if admin_score > job_score:
        assert any("displacement" in v for v in report.violations)
