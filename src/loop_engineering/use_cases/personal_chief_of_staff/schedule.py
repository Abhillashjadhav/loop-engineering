"""Scheduling engine: propose focus blocks in real free time only.

Reads actual calendar events, computes free gaps inside working hours,
protects existing meetings, and packs prioritized tasks into non-overlapping
blocks with buffer/transition time. Never schedules beyond available free
time; when the day is overloaded it returns the blocks that fit plus an
explicit overflow list and an alternative suggestion. Focus blocks are only
*proposed* here — creation happens in the executor after one approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from loop_engineering.use_cases.personal_chief_of_staff.models import (
    CalendarItem,
    Flexibility,
    SourceType,
)
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import ScoredTask

BUFFER_MIN = 10  # transition/buffer time between blocks
MIN_BLOCK_MIN = 25  # don't fragment below this


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


@dataclass
class FocusBlock:
    task_id: str
    title: str
    start: str
    end: str

    def to_calendar_item(self) -> CalendarItem:
        return CalendarItem(
            event_id=f"focus-{self.task_id}",
            title=f"[Focus] {self.title}",
            start=self.start,
            end=self.end,
            attendees=[],
            flexibility=Flexibility.FOCUS_BLOCK,
            source=SourceType.CALENDAR,
        )


@dataclass
class ProposedSchedule:
    day: str
    blocks: list[FocusBlock] = field(default_factory=list)
    overflow: list[str] = field(default_factory=list)  # task ids that did not fit
    free_minutes: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "day": self.day,
            "blocks": [
                {"task_id": b.task_id, "title": b.title, "start": b.start, "end": b.end}
                for b in self.blocks
            ],
            "overflow": list(self.overflow),
            "free_minutes": self.free_minutes,
            "note": self.note,
        }


def free_gaps(
    events: list[CalendarItem], day: str, work_start: str = "09:00", work_end: str = "18:00"
) -> list[tuple[datetime, datetime]]:
    """Free intervals inside working hours, with existing meetings removed.

    Events are matched by INTERVAL INTERSECTION with the working window in
    absolute (timezone-aware) time — never by start-date string equality — so
    overnight/multi-day events and events expressed in other UTC offsets
    still block the time they actually cover (review finding #1).
    """
    start = _dt(f"{day}T{work_start}:00+00:00")
    end = _dt(f"{day}T{work_end}:00+00:00")
    busy: list[tuple[datetime, datetime]] = []
    for e in events:
        if not e.busy:  # transparent/free events never consume free time
            continue
        e_start, e_end = _dt(e.start), _dt(e.end)
        lo, hi = max(e_start, start), min(e_end, end)
        if lo < hi:  # the event overlaps the working window
            busy.append((lo, hi))
    busy.sort(key=lambda x: x[0])
    gaps: list[tuple[datetime, datetime]] = []
    cursor = start
    for b_start, b_end in busy:
        if b_start > cursor:
            gaps.append((cursor, min(b_start, end)))
        cursor = max(cursor, b_end)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return [(s, e) for s, e in gaps if (e - s).total_seconds() / 60 >= MIN_BLOCK_MIN]


def propose_schedule(
    scored: list[ScoredTask], events: list[CalendarItem], day: str
) -> ProposedSchedule:
    """Pack highest-priority tasks into real free gaps. Deterministic."""
    gaps = free_gaps(events, day)
    free_minutes = int(sum((e - s).total_seconds() / 60 for s, e in gaps))
    sched = ProposedSchedule(day=day, free_minutes=free_minutes)

    gap_cursors = [list(g) for g in gaps]  # mutable [start, end]
    for st in scored:
        need = max(MIN_BLOCK_MIN, st.task.estimated_minutes)
        placed = False
        for gc in gap_cursors:
            avail = (gc[1] - gc[0]).total_seconds() / 60
            if avail >= need:
                b_start = gc[0]
                b_end = b_start + timedelta(minutes=need)
                sched.blocks.append(
                    FocusBlock(
                        task_id=st.task.id,
                        title=st.task.title,
                        start=b_start.isoformat(),
                        end=b_end.isoformat(),
                    )
                )
                gc[0] = b_end + timedelta(minutes=BUFFER_MIN)  # buffer after block
                placed = True
                break
        if not placed:
            sched.overflow.append(st.task.id)

    if sched.overflow:
        sched.note = (
            f"{len(sched.overflow)} task(s) did not fit in {free_minutes} min of free time; "
            "consider deferring lower-priority work or protecting a longer focus window tomorrow."
        )
    else:
        sched.note = f"All proposed work fits within {free_minutes} min of free time."
    return sched


def has_overlap(blocks: list[FocusBlock]) -> bool:
    """True if any two blocks overlap (invariant: must always be False)."""
    from itertools import pairwise

    ordered = sorted(blocks, key=lambda b: b.start)
    return any(_dt(a.end) > _dt(b.start) for a, b in pairwise(ordered))
