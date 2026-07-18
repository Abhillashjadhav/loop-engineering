"""Determinism (byte-identical reports) + the north-star no-loss guard."""

from __future__ import annotations

from pathlib import Path

from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
    FixtureCalendarAdapter,
    FixtureSourceAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.dashboard import render_dashboard
from loop_engineering.use_cases.personal_chief_of_staff.models import AdapterMode
from loop_engineering.use_cases.personal_chief_of_staff.runner import ChiefOfStaff

DEMO = Path("use_cases/personal-chief-of-staff/demo")
SOURCES = ("email", "github", "drive", "chat_context", "manual")


def _cos() -> ChiefOfStaff:
    src = [FixtureSourceAdapter(n, DEMO, mode=AdapterMode.FIXTURE) for n in SOURCES]
    return ChiefOfStaff(src, FixtureCalendarAdapter(DEMO))


def test_identical_inputs_produce_byte_identical_reports() -> None:
    a = _cos().run("run-x", "2026-07-17", "2026-07-17T08:00:00+00:00")
    b = _cos().run("run-x", "2026-07-17", "2026-07-17T08:00:00+00:00")
    assert a.briefs == b.briefs, "planted failure: non-deterministic briefs"
    assert render_dashboard(a) == render_dashboard(b), (
        "planted failure: non-deterministic dashboard"
    )
    import json

    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_no_datetime_now_in_report_modules() -> None:
    # Determinism guard: report/runtime modules must not CALL the wall clock.
    # Prose mentions inside backtick spans (docstrings) are ignored — only real
    # call sites (``datetime.now(`` / ``utcnow(``) count.
    import re

    import loop_engineering.use_cases.personal_chief_of_staff as pkg

    root = Path(pkg.__file__).parent
    backtick_span = re.compile(r"`[^`]*`")
    for name in ("briefs.py", "runner.py", "dashboard.py", "schedule.py", "checkpoint.py"):
        text = (root / name).read_text(encoding="utf-8")
        # Collapse RST double-backtick runs to single, then strip backtick spans
        # so only real code (not docstring mentions) is checked.
        code = backtick_span.sub("", re.sub(r"`+", "`", text))
        assert "datetime.now(" not in code, f"planted failure: {name} calls datetime.now()"
        assert "utcnow(" not in code, f"planted failure: {name} calls utcnow()"


def test_north_star_no_commitment_lost_between_ingestion_and_brief() -> None:
    cos = _cos()
    raw = [item for a in cos.sources for item in a.fetch()]
    result = cos.run("run-ns", "2026-07-17", "2026-07-17T08:00:00+00:00")

    # Every external-commitment source reference that produced a task must be
    # traceable in the register AND appear somewhere in the day's briefs.
    external_refs = {
        i.reference
        for i in raw
        if i.meta.get("external_commitment") or i.meta.get("kind") == "review_request"
    }
    register_refs = {s.source_reference for t in result.register.tasks for s in t.sources}
    for ref in external_refs:
        assert ref in register_refs, f"north-star violation: {ref} lost before the register"

    all_briefs = "\n".join(result.briefs.values())
    # The interview and recruiter commitments must surface in the morning brief.
    assert "interview" in all_briefs.lower()
    assert "resume" in all_briefs.lower() or "references" in all_briefs.lower()


def test_every_registered_task_keeps_source_and_confidence() -> None:
    result = _cos().run("run-src", "2026-07-17", "2026-07-17T08:00:00+00:00")
    for t in result.register.tasks:
        assert t.sources, "planted failure: registered task without source"
        assert 0.0 < t.confidence <= 1.0
        d = t.to_dict()
        assert d["sources"][0]["source_excerpt"]
        assert d["inferred_or_explicit"] in ("explicit", "inferred")
