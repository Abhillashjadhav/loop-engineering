"""Regression tests for the independent-review blocking findings (PR #14)."""

from __future__ import annotations

from pathlib import Path

from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import RawItem
from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
    FixtureCalendarAdapter,
    FixtureSourceAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.checkpoint import drift_check
from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.discovery import (
    _normalize_deadline,
    discover,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    AdapterMode,
    CalendarItem,
    DecisionCheckpoint,
    Energy,
    Origin,
    SourceType,
    Task,
    TaskSource,
    TaskStatus,
)
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import prioritize
from loop_engineering.use_cases.personal_chief_of_staff.registry import TaskRegister
from loop_engineering.use_cases.personal_chief_of_staff.runner import ChiefOfStaff
from loop_engineering.use_cases.personal_chief_of_staff.schedule import (
    free_gaps,
    propose_schedule,
)

DAY = "2026-07-17"
NOW = "2026-07-17T08:00:00+00:00"
DEMO = Path("use_cases/personal-chief-of-staff/demo")


def _task(tid: str, title: str, status: TaskStatus = TaskStatus.ACTIVE, minutes: int = 60) -> Task:
    return Task(
        id=tid,
        title=title,
        description=title,
        sources=[
            TaskSource(
                source_type=SourceType.MANUAL,
                source_reference=f"ref-{tid}",
                source_excerpt=title,
                inferred_or_explicit=Origin.EXPLICIT,
                confidence=0.9,
            )
        ],
        estimated_minutes=minutes,
        energy=Energy.MEDIUM,
        status=status,
    )


# --- Finding 1: interval intersection, not start-date string equality --------


def test_overnight_event_blocks_the_morning() -> None:
    overnight = CalendarItem(
        "ov", "Red-eye + recovery", "2026-07-16T20:00:00+00:00", f"{DAY}T10:30:00+00:00", ["x@y"]
    )
    gaps = free_gaps([overnight], DAY)
    # No free time may exist before 10:30.
    assert all(s.isoformat() >= f"{DAY}T10:30:00+00:00" for s, _ in gaps), (
        "review finding 1: overnight event treated as free time"
    )


def test_event_in_other_utc_offset_still_blocks() -> None:
    # 2026-07-18T01:00+09:00 == 2026-07-17T16:00Z — must block 16:00-17:00Z.
    offset_event = CalendarItem(
        "tz", "APAC call", "2026-07-18T01:00:00+09:00", "2026-07-18T02:00:00+09:00", ["x@y"]
    )
    scored = prioritize([_task("t1", "Deep work", minutes=480)], OperatingContract(), DAY)
    sched = propose_schedule(scored, [offset_event], DAY)
    for b in sched.blocks:
        assert not (b.start < f"{DAY}T17:00:00+00:00" and b.end > f"{DAY}T16:00:00+00:00"), (
            "review finding 1: differently-offset event ignored"
        )


# --- Finding 2: deadlines normalized to ISO, comparisons well-defined --------


def test_slash_deadline_normalizes_and_is_not_falsely_overdue() -> None:
    tasks = discover([RawItem("email", "m1", "Slides", "I will send the slides by 12/1.")], NOW)
    assert tasks[0].deadline == "2026-12-01"
    reg = TaskRegister(tasks)
    assert reg.overdue(DAY) == [], "review finding 2: December deadline reported overdue in July"


def test_relative_deadlines_resolve_deterministically() -> None:
    assert _normalize_deadline("tomorrow", NOW) == "2026-07-18"
    assert _normalize_deadline("today", NOW) == "2026-07-17"
    assert _normalize_deadline("next week", NOW) == "2026-07-24"
    # 2026-07-17 is a Friday; "friday" = NEXT Friday, never today.
    assert _normalize_deadline("friday", NOW) == "2026-07-24"
    assert _normalize_deadline("monday", NOW) == "2026-07-20"
    assert _normalize_deadline("3/1/27", NOW) == "2027-03-01"
    assert _normalize_deadline("13/45", NOW) is None  # not a date → no invention
    # "by tomorrow" can become overdue the day after.
    t = discover([RawItem("email", "m2", "x", "I need to reply by tomorrow.")], NOW)
    assert TaskRegister(t).overdue("2026-07-19"), (
        "review finding 2: relative deadline never overdue"
    )


# --- Finding 3: prior prohibited actions are enforced and can fire -----------


def test_prior_prohibited_action_matches_natural_language() -> None:
    prior = DecisionCheckpoint(timestamp=NOW, prohibited_actions=["send_email"])
    scored = prioritize(
        [_task("t1", "Send the follow-up email to the VC directly")],
        OperatingContract(),
        DAY,
    )
    report = drift_check(scored, OperatingContract(), prior=prior)
    assert any("revisits a prohibited action" in v for v in report.violations), (
        "review finding 3: snake_case prohibited action failed to match natural language"
    )


def test_runner_threads_prior_checkpoint_into_drift() -> None:
    src = [
        FixtureSourceAdapter(n, DEMO, mode=AdapterMode.FIXTURE)
        for n in ("email", "github", "drive", "chat_context", "manual")
    ]
    cos = ChiefOfStaff(src, FixtureCalendarAdapter(DEMO))
    prior = DecisionCheckpoint(timestamp=NOW, prohibited_actions=["submit talk proposal"])
    result = cos.run("r1", DAY, NOW, prior_checkpoint=prior)
    # The demo contains "I need to submit a talk proposal…" — must be flagged.
    assert any("revisits a prohibited action" in v for v in result.drift.violations)


# --- Scheduling packs only actionable work (review finding 5) ----------------


def test_blocked_waiting_inbox_tasks_never_consume_focus_blocks() -> None:
    src = [
        FixtureSourceAdapter(n, DEMO, mode=AdapterMode.FIXTURE)
        for n in ("email", "github", "drive", "chat_context", "manual")
    ]
    cos = ChiefOfStaff(src, FixtureCalendarAdapter(DEMO))
    result = cos.run("r2", DAY, NOW)
    non_active = {t.id for t in result.register.tasks if t.status is not TaskStatus.ACTIVE}
    scheduled = {b.task_id for b in result.schedule.blocks}
    assert not (scheduled & non_active), "non-actionable task consumed a focus block"


# --- Honesty: executed safe actions carry the real artifact (finding 7) ------


def test_executed_actions_carry_generated_artifact_not_bare_claim() -> None:
    src = [
        FixtureSourceAdapter(n, DEMO, mode=AdapterMode.FIXTURE)
        for n in ("email", "github", "drive", "chat_context", "manual")
    ]
    cos = ChiefOfStaff(src, FixtureCalendarAdapter(DEMO))
    result = cos.run("r3", DAY, NOW)
    for a in result.safe_result.executed:
        assert "performed" not in a.execution_evidence
        assert any(
            marker in a.execution_evidence
            for marker in (
                "DRAFT (not sent)",
                "PREP SESSION",
                "ISSUE DRAFT",
                "PREPARED",
                "MEETING BRIEF",
                "REMINDER",
            )
        ), f"evidence is not an artifact: {a.execution_evidence!r}"
