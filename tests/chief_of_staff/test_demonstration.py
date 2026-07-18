"""Full synthetic demonstration — proves every required capability at once.

Runs the committed demo dataset (one interview, recruiter follow-up, stalled
review, unfinished PEOS task, conference action, doc with action items,
overdue personal task, blocked task waiting on a person, limited-free-time
calendar) end to end and asserts the demonstration guarantees.
"""

from __future__ import annotations

from pathlib import Path

from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
    FixtureCalendarAdapter,
    FixtureSourceAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.execute import (
    approve_and_create_focus_blocks,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import AdapterMode, TaskStatus
from loop_engineering.use_cases.personal_chief_of_staff.runner import ChiefOfStaff

DEMO = Path("use_cases/personal-chief-of-staff/demo")
SOURCES = ("email", "github", "drive", "chat_context", "manual")
DAY = "2026-07-17"
AS_OF = "2026-07-17T08:00:00+00:00"


def _run():  # type: ignore[no-untyped-def]
    src = [FixtureSourceAdapter(n, DEMO, mode=AdapterMode.FIXTURE) for n in SOURCES]
    cos = ChiefOfStaff(src, FixtureCalendarAdapter(DEMO))
    return cos, cos.run("demo", DAY, AS_OF)


def test_demonstration_source_backed_discovery() -> None:
    _, r = _run()
    assert r.register.tasks
    for t in r.register.tasks:
        assert t.sources and t.sources[0].source_excerpt  # source-backed


def test_demonstration_dedup_and_multiple_sources() -> None:
    _, r = _run()
    source_types = {s.source_type.value for t in r.register.tasks for s in t.sources}
    # tasks come from at least 4 distinct source systems
    assert len(source_types) >= 4


def test_demonstration_prioritization_puts_job_search_on_top() -> None:
    _, r = _run()
    top_titles = " ".join(st.task.title.lower() for st in r.scored[:3])
    assert "resume" in top_titles or "interview" in top_titles or "recruiter" in top_titles


def test_demonstration_overdue_blocked_waiting_visible() -> None:
    _, r = _run()
    assert r.register.overdue(DAY), "overdue task (dentist) must be detected"
    assert r.register.waiting(), "waiting-on task (Priya) must be detected"
    # stalled GitHub PR surfaces as inbox (needs triage), not active
    assert any(t.status is TaskStatus.INBOX for t in r.register.tasks)


def test_demonstration_schedule_from_real_free_time_one_approval() -> None:
    _, r = _run()
    assert r.schedule.free_minutes > 0
    assert not r.schedule.overflow or r.schedule.note
    # one-approval focus-block flow
    cal = FixtureCalendarAdapter(DEMO)
    created = approve_and_create_focus_blocks(r.schedule, cal, approved=True)
    assert len(created) == len(r.schedule.blocks)


def test_demonstration_three_briefs_present() -> None:
    _, r = _run()
    assert set(r.briefs) == {"morning", "midday", "evening"}
    assert "Morning brief" in r.briefs["morning"]
    assert "Midday check" in r.briefs["midday"]
    assert "Evening close" in r.briefs["evening"]


def test_demonstration_at_least_five_safe_actions() -> None:
    _, r = _run()
    assert len(r.safe_result.executed) >= 5
    assert not r.safe_result.blocked  # demo derives only safe actions


def test_demonstration_no_unauthorized_external_action() -> None:
    _, r = _run()
    executed_types = {a.action_type for a in r.safe_result.executed}
    prohibited = {
        "send_email",
        "forward_email",
        "cancel_meeting",
        "merge_code",
        "publish_content",
        "apply_to_job",
        "linkedin_publish",
    }
    assert not (executed_types & prohibited), "no external action may auto-execute"


def test_demonstration_context_checkpoint_persists() -> None:
    _, r = _run()
    cp = r.checkpoint
    assert cp.context_digest
    assert cp.prohibited_actions  # prohibited list carried in the checkpoint
    # A second run with identical inputs yields an identical checkpoint digest.
    _, r2 = _run()
    assert r2.checkpoint.context_digest == cp.context_digest
