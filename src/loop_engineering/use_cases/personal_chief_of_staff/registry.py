"""Unified task register + dedup.

Dedup merges near-identical commitments WITHOUT losing provenance: the merged
task keeps every source. Two tasks are duplicates when their normalized
titles match closely and they share a project/waiting-on context. Manual and
explicit tasks are never silently dropped in favor of an inferred twin — the
higher-confidence origin wins the surviving record, but all sources merge.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from loop_engineering.use_cases.personal_chief_of_staff.models import Task, TaskStatus

_STOP = re.compile(r"[^a-z0-9 ]+")


def _norm(title: str) -> str:
    return _STOP.sub("", title.lower()).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _merge(primary: Task, other: Task) -> Task:
    """Fold ``other`` into ``primary``, unioning sources and keeping the
    strongest available signal on each field."""
    seen = {(s.source_type, s.source_reference, s.source_excerpt) for s in primary.sources}
    for s in other.sources:
        key = (s.source_type, s.source_reference, s.source_excerpt)
        if key not in seen:
            primary.sources.append(s)
            seen.add(key)
    primary.goal_ids = sorted(set(primary.goal_ids) | set(other.goal_ids))
    primary.dependency_ids = sorted(set(primary.dependency_ids) | set(other.dependency_ids))
    # Deadlines: keep the earliest real deadline; never invent one.
    if other.deadline and (primary.deadline is None or other.deadline < primary.deadline):
        primary.deadline = other.deadline
    primary.external_commitment = primary.external_commitment or other.external_commitment
    primary.estimated_minutes = max(primary.estimated_minutes, other.estimated_minutes)
    if not primary.waiting_on and other.waiting_on:
        primary.waiting_on = other.waiting_on
    if not primary.project and other.project:
        primary.project = other.project
    # Status precedence is CONSERVATIVE (persistence review finding #3): a
    # dedup cluster containing a terminal member stays terminal (keeping its
    # completion evidence), and a cluster containing an INBOX member stays
    # INBOX — confirmation is required; a merge must never silently activate
    # work the user completed, rejected, or has not yet confirmed.
    statuses = (primary.status, other.status)
    if TaskStatus.DONE in statuses:
        primary.status = TaskStatus.DONE
        if not primary.evidence_of_completion and other.evidence_of_completion:
            primary.evidence_of_completion = other.evidence_of_completion
    elif TaskStatus.DROPPED in statuses:
        primary.status = TaskStatus.DROPPED
    elif TaskStatus.INBOX in statuses:
        primary.status = TaskStatus.INBOX
    return primary


def deduplicate(tasks: list[Task], threshold: float = 0.82) -> list[Task]:
    """Merge duplicate commitments, preserving all sources.

    Deterministic: input order is preserved for survivors; the
    highest-confidence task in a duplicate cluster becomes the survivor.
    """
    survivors: list[Task] = []
    for task in tasks:
        match = None
        for kept in survivors:
            same_context = (task.project or "") == (kept.project or "") and (
                (task.waiting_on or "") == (kept.waiting_on or "")
            )
            if same_context and _similar(task.title, kept.title) >= threshold:
                match = kept
                break
        if match is None:
            survivors.append(task)
            continue
        # Higher confidence wins the surviving identity; sources union either way.
        if task.confidence > match.confidence:
            idx = survivors.index(match)
            merged = _merge(task, match)
            survivors[idx] = merged
        else:
            _merge(match, task)
    return survivors


class TaskRegister:
    """The one source-backed register. Adds with dedup; queries by facet."""

    def __init__(self, tasks: list[Task] | None = None) -> None:
        self.tasks: list[Task] = deduplicate(list(tasks or []))

    def add(self, tasks: list[Task]) -> None:
        self.tasks = deduplicate(self.tasks + tasks)

    def overdue(self, today_iso: str) -> list[Task]:
        return [
            t
            for t in self.tasks
            if t.deadline and t.deadline < today_iso and t.status is not TaskStatus.DONE
        ]

    def blocked(self) -> list[Task]:
        return [t for t in self.tasks if t.status is TaskStatus.BLOCKED or t.blocked_by]

    def waiting(self) -> list[Task]:
        return [t for t in self.tasks if t.status is TaskStatus.WAITING or t.waiting_on]

    def inbox(self) -> list[Task]:
        return [t for t in self.tasks if t.status is TaskStatus.INBOX]

    def active(self) -> list[Task]:
        return [t for t in self.tasks if t.status is TaskStatus.ACTIVE]

    def to_dict(self) -> dict[str, object]:
        return {"count": len(self.tasks), "tasks": [t.to_dict() for t in self.tasks]}
