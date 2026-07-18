"""Planted-failure tests for cross-run private task-register persistence.

Written FIRST (tests-first): they define the RegisterStore contract —
append-only journal under the fail-closed private boundary, idempotent
ingestion, provenance preservation, terminal-state protection, conflict
detection, crash-safe recovery, fail-loud corruption, schema versioning,
and deterministic state.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from loop_engineering.use_cases.personal_chief_of_staff.models import (
    DecisionCheckpoint,
    Energy,
    Origin,
    SourceType,
    Task,
    TaskSource,
    TaskStatus,
)
from loop_engineering.use_cases.personal_chief_of_staff.privacy import PrivacyViolation
from loop_engineering.use_cases.personal_chief_of_staff.store import (
    ConflictError,
    CorruptStateError,
    MissingProvenanceError,
    RegisterStore,
)

NOW = "2026-07-18T08:00:00+00:00"
LATER = "2026-07-19T08:00:00+00:00"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch git repo with the private boundary in place."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("/runs/private/\n", encoding="utf-8")
    return tmp_path


def task(
    tid: str,
    title: str = "",
    excerpt: str = "",
    status: TaskStatus = TaskStatus.ACTIVE,
    confidence: float = 0.9,
    sources: list[TaskSource] | None = None,
) -> Task:
    title = title or f"Task {tid}"
    src = sources
    if src is None:
        src = [
            TaskSource(
                source_type=SourceType.EMAIL,
                source_reference=f"ref-{tid}",
                source_excerpt=excerpt or title,
                inferred_or_explicit=Origin.EXPLICIT,
                confidence=confidence,
            )
        ]
    return Task(
        id=tid,
        title=title,
        description=title,
        sources=src,
        estimated_minutes=30,
        energy=Energy.MEDIUM,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def store(repo: Path) -> RegisterStore:
    return RegisterStore(root=repo)


# 1. duplicate ingestion ------------------------------------------------------


def test_duplicate_ingestion_is_idempotent(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1"), task("t2")], NOW)
    digest_once = s.state_digest()
    events_once = s.event_count()
    s.ingest([task("t1"), task("t2")], NOW)  # identical again
    assert s.event_count() == events_once, "planted: duplicate ingestion appended events"
    assert s.state_digest() == digest_once
    assert len(s.view()) == 2


# 2. interrupted write / crash-safe resume ------------------------------------


def test_interrupted_write_recovers_to_last_valid_event(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1"), task("t2")], NOW)
    path = s.journal_path
    # Simulate a crash mid-append: a torn, half-written trailing line.
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"v": 1, "seq": 99, "kind": "observed", "payl')
    s2 = RegisterStore(root=repo)
    assert {t.id for t in s2.view()} == {"t1", "t2"}, "planted: torn tail lost valid state"
    # The store must remain appendable after recovery (crash-safe resume).
    s2.ingest([task("t3")], LATER)
    assert {t.id for t in RegisterStore(root=repo).view()} == {"t1", "t2", "t3"}


# 3. stale checkpoint / 6. conflicting updates --------------------------------


def test_stale_expectation_raises_conflict_not_silent_overwrite(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1")], NOW)
    s.set_status("t1", TaskStatus.DONE, evidence="PR merged", expected=TaskStatus.ACTIVE, at=NOW)
    # A second writer still believing the task is ACTIVE must get a conflict.
    with pytest.raises(ConflictError):
        s.set_status("t1", TaskStatus.BLOCKED, expected=TaskStatus.ACTIVE, at=LATER)
    assert s.status_of("t1") is TaskStatus.DONE, "planted: conflicting update silently won"


# 4. rejected task resurfacing ------------------------------------------------


def test_rejected_task_does_not_resurface_without_new_evidence(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1", excerpt="do the thing")], NOW)
    s.set_status("t1", TaskStatus.DROPPED, evidence="rejected: out of scope", at=NOW)
    s.ingest([task("t1", excerpt="do the thing")], LATER)  # same evidence again
    assert s.status_of("t1") is TaskStatus.DROPPED, "planted: rejected task resurfaced"


# 5. completed task reverting to active ---------------------------------------


def test_completed_task_never_silently_reactivates(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1", excerpt="ship the deck")], NOW)
    s.set_status("t1", TaskStatus.DONE, evidence="sent 2026-07-18", at=NOW)
    s.ingest([task("t1", excerpt="ship the deck")], LATER)  # same observation
    assert s.status_of("t1") is TaskStatus.DONE, "planted: completed task reverted to active"
    # NEW evidence may resurface it — but only into INBOX for confirmation,
    # never silently ACTIVE.
    s.ingest([task("t1", excerpt="please re-send the updated deck")], LATER)
    assert s.status_of("t1") is TaskStatus.INBOX
    resurfaced = next(t for t in s.view() if t.id == "t1")
    assert len(resurfaced.sources) >= 2  # old + new provenance both kept


def test_done_requires_evidence(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1")], NOW)
    with pytest.raises(ValueError, match="evidence"):
        s.set_status("t1", TaskStatus.DONE, at=NOW)  # no evidence → refuse


# 7. private path escape ------------------------------------------------------


def test_store_refuses_non_private_location(repo: Path) -> None:
    with pytest.raises(PrivacyViolation):
        RegisterStore(root=repo, relative="src/leak/journal.jsonl")
    with pytest.raises(PrivacyViolation):
        RegisterStore(root=repo, relative="runs/private/../../escape.jsonl")


def test_store_refuses_when_boundary_missing(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("# boundary removed\n", encoding="utf-8")
    with pytest.raises(PrivacyViolation):
        RegisterStore(root=tmp_path)


# 8. corrupted state ----------------------------------------------------------


def test_corrupt_middle_event_fails_loudly(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1"), task("t2"), task("t3")], NOW)
    lines = s.journal_path.read_text(encoding="utf-8").splitlines()
    # Tamper with a MIDDLE event (not the tail): silent repair is forbidden.
    mid = len(lines) // 2
    tampered = json.loads(lines[mid])
    tampered["payload"]["task"]["title"] = "tampered"
    lines[mid] = json.dumps(tampered)  # digest now wrong
    s.journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CorruptStateError):
        RegisterStore(root=repo).view()


# 9. missing provenance -------------------------------------------------------


def test_task_without_source_is_rejected(repo: Path) -> None:
    s = store(repo)
    orphan = task("t1")
    orphan.sources = []
    with pytest.raises(MissingProvenanceError):
        s.ingest([orphan], NOW)
    assert s.view() == []


# 10. repeated run determinism ------------------------------------------------


def test_repeated_load_and_view_are_byte_identical(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1"), task("t2", confidence=0.7)], NOW)
    s.set_status("t2", TaskStatus.WAITING, evidence="waiting on Dana", at=NOW)
    view_a = json.dumps([t.to_dict() for t in RegisterStore(root=repo).view()], sort_keys=True)
    view_b = json.dumps([t.to_dict() for t in RegisterStore(root=repo).view()], sort_keys=True)
    assert view_a == view_b, "planted: same journal produced different views"
    assert RegisterStore(root=repo).state_digest() == s.state_digest()


# Provenance survives round trip ----------------------------------------------


def test_every_source_and_confidence_survives_persistence(repo: Path) -> None:
    two_sources = [
        TaskSource(SourceType.EMAIL, "ref-a", "excerpt A", Origin.EXPLICIT, 0.9, "rule"),
        TaskSource(SourceType.CHAT_CONTEXT, "ref-b", "excerpt B", Origin.INFERRED, 0.6, "cue"),
    ]
    s = store(repo)
    s.ingest([task("t1", sources=two_sources)], NOW)
    restored = RegisterStore(root=repo).view()[0]
    assert [src.to_dict() for src in restored.sources] == [src.to_dict() for src in two_sources], (
        "planted: provenance lost through persistence"
    )
    assert restored.confidence == 0.9


# Dedup across observations preserves provenance ------------------------------


def test_cross_source_observations_merge_without_losing_provenance(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1", excerpt="from email")], NOW)
    chat = task(
        "t1",
        sources=[TaskSource(SourceType.CHAT_CONTEXT, "chat-1", "from chat", Origin.INFERRED, 0.6)],
    )
    s.ingest([chat], LATER)
    merged = next(t for t in s.view() if t.id == "t1")
    origins = {src.source_type for src in merged.sources}
    assert origins == {SourceType.EMAIL, SourceType.CHAT_CONTEXT}


# Checkpoint history + schema versioning --------------------------------------


def test_checkpoint_history_survives(repo: Path) -> None:
    s = store(repo)
    s.append_checkpoint(DecisionCheckpoint(timestamp=NOW, next_steps=["a"]), at=NOW)
    s.append_checkpoint(DecisionCheckpoint(timestamp=LATER, next_steps=["b"]), at=LATER)
    history = RegisterStore(root=repo).checkpoints()
    assert [c.timestamp for c in history] == [NOW, LATER]


def test_v0_journal_is_migrated_not_rejected(repo: Path) -> None:
    # A v0 journal (pre-digest format: no header, no sha) must be migrated
    # in place atomically, then load normally.
    state_dir = repo / "runs/private/cos/state"
    state_dir.mkdir(parents=True)
    v0_event = {
        "seq": 1,
        "kind": "observed",
        "at": NOW,
        "payload": {"task": task("t1").to_dict(), "obs_digest": "legacy"},
    }
    (state_dir / "journal.jsonl").write_text(json.dumps(v0_event) + "\n", encoding="utf-8")
    s = RegisterStore(root=repo)
    assert [t.id for t in s.view()] == ["t1"]
    # After migration the journal is v1: header present, every event digested.
    first = json.loads(s.journal_path.read_text(encoding="utf-8").splitlines()[0])
    assert first["kind"] == "header" and first["payload"]["schema_version"] == 1


def test_newer_schema_version_is_refused(repo: Path) -> None:
    state_dir = repo / "runs/private/cos/state"
    state_dir.mkdir(parents=True)
    header = {"v": 1, "seq": 0, "kind": "header", "at": NOW, "payload": {"schema_version": 99}}
    (state_dir / "journal.jsonl").write_text(json.dumps(header) + "\n", encoding="utf-8")
    with pytest.raises(CorruptStateError, match="schema"):
        RegisterStore(root=repo).view()


# Runner integration: deterministic briefs from the persisted register -------


def _cos():  # type: ignore[no-untyped-def]
    from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
        FixtureCalendarAdapter,
        FixtureSourceAdapter,
    )
    from loop_engineering.use_cases.personal_chief_of_staff.models import AdapterMode
    from loop_engineering.use_cases.personal_chief_of_staff.runner import ChiefOfStaff

    demo = Path("use_cases/personal-chief-of-staff/demo").resolve()
    src = [
        FixtureSourceAdapter(n, demo, mode=AdapterMode.FIXTURE)
        for n in ("email", "github", "drive", "chat_context", "manual")
    ]
    return ChiefOfStaff(src, FixtureCalendarAdapter(demo))


def test_repeated_run_over_store_is_idempotent_and_deterministic(repo: Path) -> None:
    cos = _cos()
    r1 = cos.run("p1", "2026-07-17", "2026-07-17T08:00:00+00:00", store=RegisterStore(root=repo))
    s_between = RegisterStore(root=repo)
    events_after_first = s_between.event_count()
    r2 = cos.run("p1", "2026-07-17", "2026-07-17T08:00:00+00:00", store=s_between)
    assert r1.briefs == r2.briefs, "planted: repeated run changed output without changed inputs"
    assert s_between.event_count() == events_after_first, (
        "planted: repeated run appended events with unchanged inputs"
    )


def test_status_set_between_runs_survives_into_next_brief(repo: Path) -> None:
    cos = _cos()
    r1 = cos.run("p1", "2026-07-17", "2026-07-17T08:00:00+00:00", store=RegisterStore(root=repo))
    done_id = r1.scored[0].task.id
    s = RegisterStore(root=repo)
    s.set_status(done_id, TaskStatus.DONE, evidence="sent + confirmed by reply", at=NOW)
    r2 = cos.run("p2", "2026-07-18", "2026-07-18T08:00:00+00:00", store=RegisterStore(root=repo))
    persisted = next(t for t in r2.register.tasks if done_id in {t.id})
    assert persisted.status is TaskStatus.DONE, "planted: completed state lost between runs"
    assert persisted.evidence_of_completion
    # And the completed task appears in the evening close of the NEXT run.
    assert persisted.title[:30] in r2.briefs["evening"]


# Review round 2 — blocking-finding regressions --------------------------------


def test_relative_deadline_reresolution_is_not_new_evidence(repo: Path) -> None:
    """Finding 1: the same email re-ingested on a later day (relative deadline
    re-resolved against the new clock) must NOT reopen a DONE task."""
    from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import RawItem
    from loop_engineering.use_cases.personal_chief_of_staff.discovery import discover

    item = RawItem("email", "msg-deck", "Deck", "I will send the investor deck by tomorrow.")
    s = store(repo)
    day1 = discover([item], "2026-07-18T08:00:00+00:00")
    s.ingest(day1, "2026-07-18T08:00:00+00:00")
    tid = day1[0].id
    s.set_status(tid, TaskStatus.DONE, evidence="sent, confirmed", at=NOW)
    # Same unchanged email, fetched again the next day: deadline re-resolves.
    day2 = discover([item], "2026-07-19T08:00:00+00:00")
    assert day2[0].deadline != day1[0].deadline  # precondition of the bug
    events_before = RegisterStore(root=repo).event_count()
    s2 = RegisterStore(root=repo)
    appended = s2.ingest(day2, "2026-07-19T08:00:00+00:00")
    assert appended == 0, "planted: re-resolved relative deadline treated as new evidence"
    assert s2.event_count() == events_before
    assert s2.status_of(tid) is TaskStatus.DONE


def test_torn_first_ever_append_recovers(repo: Path) -> None:
    """Finding 2: a crash during the first-ever append must recover, not
    raise raw JSONDecodeError forever."""
    state_dir = repo / "runs/private/cos/state"
    state_dir.mkdir(parents=True)
    (state_dir / "journal.jsonl").write_text('{"v": 1, "seq": 0, "kind": "hea', encoding="utf-8")
    s = RegisterStore(root=repo)  # must not raise
    assert s.view() == []
    s.ingest([task("t1")], NOW)  # and must be appendable afterwards
    assert [t.id for t in RegisterStore(root=repo).view()] == ["t1"]


def test_dedup_twin_cannot_reactivate_terminal_or_inbox_state(repo: Path) -> None:
    """Finding 3: an ACTIVE dedup twin must never silently override a DONE or
    resurfaced-INBOX twin in the register the runner plans from."""
    from loop_engineering.use_cases.personal_chief_of_staff.registry import TaskRegister

    done = task("t-a", title="Send the investor deck")
    done.status = TaskStatus.DONE
    done.evidence_of_completion = "sent + reply"
    twin = task("t-b", title="Send the investor deck!", confidence=0.95)
    reg = TaskRegister([done, twin])
    assert len(reg.tasks) == 1
    assert reg.tasks[0].status is TaskStatus.DONE, "planted: DONE dropped by dedup twin"
    assert reg.tasks[0].evidence_of_completion == "sent + reply"

    inbox = task("t-c", title="Refactor the billing job")
    inbox.status = TaskStatus.INBOX
    active_twin = task("t-d", title="Refactor the billing job.", confidence=0.95)
    reg2 = TaskRegister([inbox, active_twin])
    assert len(reg2.tasks) == 1
    assert reg2.tasks[0].status is TaskStatus.INBOX, (
        "planted: resurfaced INBOX silently promoted to ACTIVE by dedup"
    )


def test_resurfaced_task_sheds_stale_completion_evidence(repo: Path) -> None:
    s = store(repo)
    s.ingest([task("t1", excerpt="ship it")], NOW)
    s.set_status("t1", TaskStatus.DONE, evidence="shipped", at=NOW)
    s.ingest([task("t1", excerpt="actually please ship v2 as well")], LATER)
    resurfaced = next(t for t in s.view() if t.id == "t1")
    assert resurfaced.status is TaskStatus.INBOX
    assert resurfaced.evidence_of_completion == "", "stale completion evidence retained"
