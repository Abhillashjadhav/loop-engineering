"""Morning / midday / evening Chief of Staff briefs.

Deterministic: the report timestamp is bound to immutable run metadata
(``run_id`` + a supplied ``as_of`` clock), never ``datetime.now()``. Identical
inputs produce byte-identical briefs. Every task line shows its source and
confidence, so a brief is always auditable back to evidence.
"""

from __future__ import annotations

from loop_engineering.use_cases.personal_chief_of_staff.checkpoint import DriftReport
from loop_engineering.use_cases.personal_chief_of_staff.models import CalendarItem, Task
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import ScoredTask
from loop_engineering.use_cases.personal_chief_of_staff.schedule import ProposedSchedule


def _task_line(task: Task) -> str:
    src = task.sources[0] if task.sources else None
    tag = "explicit" if not task.is_inferred else "inferred"
    conf = f"{task.confidence:.2f}"
    where = f"{src.source_type.value}:{src.source_reference}" if src else "no-source"
    dead = f" ⏰{task.deadline}" if task.deadline else ""
    return f"- {task.title}{dead}  ·  [{tag} {conf} · {where}]"


def _section(title: str, tasks: list[Task]) -> list[str]:
    lines = [f"### {title}", ""]
    if not tasks:
        lines.append("- (none)")
    else:
        lines.extend(_task_line(t) for t in tasks)
    lines.append("")
    return lines


def morning_brief(
    run_id: str,
    as_of: str,
    day: str,
    scored: list[ScoredTask],
    events: list[CalendarItem],
    overdue: list[Task],
    blocked: list[Task],
    schedule: ProposedSchedule,
    safe_action_titles: list[str],
    drift: DriftReport,
) -> str:
    top3 = [st.task for st in scored[:3]]
    externals = [e for e in events if e.has_external_attendees]
    lines = [
        f"# Morning brief — {day}",
        f"_run {run_id} · as of {as_of} · deterministic_",
        "",
        "## Today's external commitments",
        "",
        *(
            [f"- {e.title} ({e.start}→{e.end}) with {', '.join(e.attendees)}" for e in externals]
            or ["- (none)"]
        ),
        "",
        *_section("Top 3 outcomes", top3),
        *_section("Overdue / forgotten", overdue),
        *_section("Blocked work", blocked),
        "## Proposed focus blocks (needs one approval to create)",
        "",
        *(
            [f"- [Focus] {b.title}: {b.start}→{b.end}" for b in schedule.blocks]
            or ["- (no free blocks proposed)"]
        ),
        f"\n_{schedule.note}_",
        "",
        "## Safe actions ready to run",
        "",
        *([f"- {t}" for t in safe_action_titles] or ["- (none)"]),
        "",
        "## Risks to today",
        "",
        *(
            [f"- ⚠️ {v}" for v in drift.violations] + [f"- {w}" for w in drift.warnings]
            or ["- none detected"]
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


def midday_check(
    run_id: str,
    as_of: str,
    day: str,
    completed: list[Task],
    slipped: list[Task],
    new_urgent: list[Task],
    waiting: list[Task],
    schedule_note: str,
) -> str:
    lines = [
        f"# Midday check — {day}",
        f"_run {run_id} · as of {as_of} · deterministic_",
        "",
        *_section("Completed so far", completed),
        *_section("Slipped", slipped),
        *_section("New urgent commitments", new_urgent),
        *_section("Waiting on other people", waiting),
        "## Schedule recovery",
        "",
        f"- {schedule_note}",
        "- Focus-block adjustments (if any) require approval before changes.",
        "",
    ]
    return "\n".join(lines) + "\n"


def evening_close(
    run_id: str,
    as_of: str,
    day: str,
    completed: list[Task],
    incomplete: list[Task],
    carried: list[Task],
    waiting: list[Task],
    tomorrow_first: Task | None,
    checkpoint_digest: str,
    forgetting_risks: list[str],
) -> str:
    lines = [
        f"# Evening close — {day}",
        f"_run {run_id} · as of {as_of} · deterministic_",
        "",
        *_section("Completed outcomes", completed),
        *_section("Incomplete (with reason below)", incomplete),
    ]
    for t in incomplete:
        reason = t.blocked_by or t.waiting_on or "not reached today"
        lines.append(f"  - {t.title}: {reason}")
    lines += [
        "",
        *_section("Commitments carried forward", carried),
        *_section("Waiting-on list", waiting),
        "## Tomorrow's first task",
        "",
        f"- {tomorrow_first.title if tomorrow_first else '(none)'}",
        "",
        "## Decision & context checkpoint",
        "",
        f"- {checkpoint_digest}",
        "",
        "## Risks of forgetting",
        "",
        *([f"- {r}" for r in forgetting_risks] or ["- none"]),
        "",
    ]
    return "\n".join(lines) + "\n"
