"""Task discovery: turn raw source items into source-backed tasks.

Explicit extraction rules only — every produced task keeps the exact
supporting text, its source, a confidence, and (when inferred) the reason it
was inferred. Deadlines are only set when the text actually states one; a
deadline is never invented. Informational content with no commitment cue
yields no task (guards against inferring work from an FYI email).
"""

from __future__ import annotations

import re

from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import RawItem
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    Energy,
    Origin,
    SourceType,
    Task,
    TaskSource,
    TaskStatus,
)

# (pattern, confidence, origin, reason). Ordered; first match wins per line.
COMMITMENT_RULES: tuple[tuple[re.Pattern[str], float, Origin, str], ...] = (
    (re.compile(r"\bI will\b", re.I), 0.9, Origin.EXPLICIT, "first-person commitment 'I will'"),
    (re.compile(r"\bI'll\b", re.I), 0.9, Origin.EXPLICIT, 'first-person commitment "I\'ll"'),
    (re.compile(r"\bI need to\b", re.I), 0.85, Origin.EXPLICIT, "stated need 'I need to'"),
    (re.compile(r"\bI have to\b", re.I), 0.8, Origin.EXPLICIT, "obligation 'I have to'"),
    (re.compile(r"\bplease send\b", re.I), 0.85, Origin.EXPLICIT, "direct request 'please send'"),
    (re.compile(r"\bfollow[- ]up\b", re.I), 0.7, Origin.INFERRED, "follow-up cue"),
    (re.compile(r"\bcan you\b", re.I), 0.55, Origin.INFERRED, "request 'can you'"),
    (re.compile(r"\bwaiting (?:on|for)\b", re.I), 0.65, Origin.INFERRED, "waiting-on cue"),
    (re.compile(r"\bblocked (?:on|by)\b", re.I), 0.7, Origin.INFERRED, "blocker cue"),
    (re.compile(r"\bneeds? review\b", re.I), 0.75, Origin.INFERRED, "review request"),
    (re.compile(r"\bnext step", re.I), 0.7, Origin.INFERRED, "checkpoint next step"),
    (re.compile(r"\baction item", re.I), 0.8, Origin.EXPLICIT, "explicit action item"),
    (re.compile(r"\bTODO\b"), 0.8, Origin.EXPLICIT, "explicit TODO marker"),
)

# Deadlines are only extracted when present — never synthesized.
_DEADLINE = re.compile(
    r"\b(?:by|due|before|deadline[:]?)\s+"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*|tomorrow|today|next week)",
    re.I,
)

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _normalize_deadline(raw: str, as_of_iso: str) -> str | None:
    """Normalize an extracted deadline cue to an ISO date (review finding #2).

    Every stored deadline is ISO ``YYYY-MM-DD`` so downstream comparisons
    (overdue detection, priority, merge-earliest) are well-defined. Relative
    forms resolve deterministically against the supplied ``as_of`` clock —
    normalization of stated text, never invention. Unparseable cues return
    None (no deadline) rather than a guess.
    """
    from datetime import date, timedelta

    token = raw.strip().lower()
    today = date.fromisoformat(as_of_iso[:10])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
        return token
    if token == "today":
        return today.isoformat()
    if token == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if token == "next week":
        return (today + timedelta(days=7)).isoformat()
    for i, prefix in enumerate(_WEEKDAYS):
        if token.startswith(prefix):
            ahead = (i - today.weekday()) % 7 or 7  # next occurrence, 1..7 days out
            return (today + timedelta(days=ahead)).isoformat()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", token)
    if m:
        month, dom = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            candidate = date(year, month, dom)
        except ValueError:
            return None  # not a real date — record nothing rather than guess
        if not m.group(3) and candidate < today:
            candidate = date(year + 1, month, dom)
        return candidate.isoformat()
    return None


_WAITING = re.compile(r"\bwaiting (?:on|for)\s+([A-Z][a-z]+)", re.I)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\n])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _norm_source_type(raw: str) -> SourceType:
    try:
        return SourceType(raw)
    except ValueError:
        mapping = {
            "email": SourceType.EMAIL,
            "gmail": SourceType.EMAIL,
            "calendar": SourceType.CALENDAR,
            "google_calendar": SourceType.CALENDAR,
            "github": SourceType.GITHUB,
            "drive": SourceType.DRIVE_DOC,
            "drive_doc": SourceType.DRIVE_DOC,
            "chat_context": SourceType.CHAT_CONTEXT,
            "project_checkpoint": SourceType.PROJECT_CHECKPOINT,
            "manual": SourceType.MANUAL,
        }
        return mapping.get(raw.lower(), SourceType.MANUAL)


def _make_id(reference: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", reference.lower()).strip("-")
    return f"t-{slug}-{index}"[:80]


def discover_from_item(item: RawItem, now_iso: str) -> list[Task]:
    """Extract zero or more tasks from one raw item using the rules above."""
    src_type = _norm_source_type(item.source_type)
    tasks: list[Task] = []
    idx = 0

    # GitHub items are structurally actionable: an open PR / review request /
    # issue IS the task (explicit), not a text inference — unless marked stale.
    if src_type is SourceType.GITHUB and item.meta.get("kind") in {
        "open_pr",
        "review_request",
        "issue",
    }:
        stale = bool(item.meta.get("stale"))
        confidence = 0.5 if stale else 0.9
        reason = (
            "stale GitHub item (no activity) — treat as needs-triage, not active"
            if stale
            else f"structural GitHub {item.meta.get('kind')}"
        )
        task = Task(
            id=_make_id(item.reference, idx),
            title=item.title or item.reference,
            description=item.body,
            sources=[
                TaskSource(
                    source_type=SourceType.GITHUB,
                    source_reference=item.reference,
                    source_excerpt=(item.title or item.body)[:280],
                    inferred_or_explicit=(Origin.INFERRED if stale else Origin.EXPLICIT),
                    confidence=confidence,
                    inference_reason=reason,
                )
            ],
            project=str(item.meta.get("project", "")),
            waiting_on=str(item.meta.get("waiting_on", "")),
            status=TaskStatus.INBOX if stale else TaskStatus.ACTIVE,
            external_commitment=item.meta.get("kind") == "review_request",
            estimated_minutes=int(item.meta.get("estimated_minutes", 30)),
            created_at=now_iso,
            updated_at=now_iso,
        )
        tasks.append(task)
        return tasks

    text = f"{item.title}. {item.body}".strip()
    for sentence in _sentences(text):
        matched = next(
            ((c, o, r) for pat, c, o, r in COMMITMENT_RULES if pat.search(sentence)),
            None,
        )
        if matched is None:
            continue
        confidence, origin, reason = matched
        deadline = None
        dm = _DEADLINE.search(sentence)
        if dm:
            deadline = _normalize_deadline(dm.group(1), now_iso)
        wm = _WAITING.search(sentence)
        waiting_on = wm.group(1) if wm else str(item.meta.get("waiting_on", ""))
        status = TaskStatus.WAITING if waiting_on else TaskStatus.ACTIVE
        if confidence < 0.6:
            status = TaskStatus.INBOX  # below confirm threshold → inbox
        tasks.append(
            Task(
                id=_make_id(item.reference, idx),
                title=sentence[:120],
                description=sentence,
                sources=[
                    TaskSource(
                        source_type=src_type,
                        source_reference=item.reference,
                        source_excerpt=sentence[:280],
                        inferred_or_explicit=origin,
                        confidence=confidence,
                        inference_reason=reason,
                    )
                ],
                project=str(item.meta.get("project", "")),
                deadline=deadline,
                external_commitment=bool(item.meta.get("external_commitment", False)),
                estimated_minutes=int(item.meta.get("estimated_minutes", 30)),
                energy=Energy(item.meta.get("energy", "medium")),
                waiting_on=waiting_on,
                status=status,
                created_at=now_iso,
                updated_at=now_iso,
            )
        )
        idx += 1
    return tasks


def discover(items: list[RawItem], now_iso: str) -> list[Task]:
    out: list[Task] = []
    for item in items:
        out.extend(discover_from_item(item, now_iso))
    return out
