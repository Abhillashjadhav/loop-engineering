"""Planted-failure regression tests for discovery, dedup, and prioritization."""

from __future__ import annotations

from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import RawItem
from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.discovery import discover
from loop_engineering.use_cases.personal_chief_of_staff.models import Origin, TaskStatus
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import prioritize
from loop_engineering.use_cases.personal_chief_of_staff.registry import TaskRegister

NOW = "2026-07-17T08:00:00+00:00"
TODAY = "2026-07-17"


def test_every_task_has_a_source() -> None:
    items = [RawItem("email", "msg-1", "Re: deck", "I will send the deck by 2026-07-20.")]
    tasks = discover(items, NOW)
    assert tasks
    for t in tasks:
        assert t.sources, "planted failure: task without a source"
        assert t.sources[0].source_excerpt


def test_deadline_never_invented() -> None:
    # No deadline cue in the text → deadline must stay None (never synthesized).
    items = [RawItem("email", "msg-2", "Thoughts", "I will refactor the scheduler at some point.")]
    tasks = discover(items, NOW)
    assert tasks and all(t.deadline is None for t in tasks), "planted failure: invented deadline"
    # A real cue IS extracted.
    dated = discover([RawItem("email", "m3", "x", "I need to reply by 2026-07-19.")], NOW)
    assert dated[0].deadline == "2026-07-19"


def test_informational_email_yields_no_task() -> None:
    items = [
        RawItem(
            "email",
            "newsletter-1",
            "Weekly AI news",
            "Here are the top papers this week. The weather is nice. FYI only.",
        )
    ]
    assert discover(items, NOW) == [], "planted failure: task inferred from informational email"


def test_stale_github_item_is_not_active() -> None:
    items = [
        RawItem(
            "github",
            "repo#12",
            "Old PR",
            "",
            meta={"kind": "open_pr", "stale": True},
        )
    ]
    tasks = discover(items, NOW)
    assert tasks[0].status is TaskStatus.INBOX
    assert tasks[0].is_inferred, "planted failure: stale GitHub task treated as active/explicit"


def test_duplicate_commitment_merges_preserving_provenance() -> None:
    items = [
        RawItem("email", "msg-a", "Deck", "I will send the deck to the recruiter."),
        RawItem("chat_context", "chat-a", "Note", "I will send the deck to the recruiter."),
    ]
    reg = TaskRegister(discover(items, NOW))
    assert len(reg.tasks) == 1, "planted failure: duplicate commitment not merged"
    assert len(reg.tasks[0].sources) == 2, "planted failure: dedup dropped provenance"
    origins = {s.source_type.value for s in reg.tasks[0].sources}
    assert origins == {"email", "chat_context"}


def test_low_value_task_cannot_outrank_interview_prep() -> None:
    items = [
        RawItem(
            "email",
            "recruiter-1",
            "Interview Tuesday",
            "I need to prepare for the Principal AI PM interview.",
            meta={"external_commitment": True, "estimated_minutes": 90},
        ),
        RawItem(
            "manual",
            "manual-1",
            "Expenses",
            "I need to file my expense report admin paperwork.",
            meta={"estimated_minutes": 10},
        ),
    ]
    tasks = discover(items, NOW)
    ranked = prioritize(tasks, OperatingContract(), TODAY)
    top = ranked[0].task
    assert "interview" in top.title.lower(), (
        "planted failure: low-value admin task outranked interview preparation"
    )
    assert ranked[0].category in ("job_search", "external_commitment")


def test_source_uncertainty_is_preserved_not_promoted_to_fact() -> None:
    # A low-confidence 'can you' request stays inferred + below-threshold (inbox),
    # never silently promoted to an explicit fact.
    items = [RawItem("email", "msg-x", "Q", "Can you look into the latency issue?")]
    tasks = discover(items, NOW)
    assert tasks[0].sources[0].inferred_or_explicit is Origin.INFERRED
    assert tasks[0].confidence < 0.7
    assert tasks[0].status is TaskStatus.INBOX
