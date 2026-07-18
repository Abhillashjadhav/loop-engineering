"""Chief of Staff CLI subcommands (deterministic).

    loop-engineering chief-of-staff ingest
    loop-engineering chief-of-staff tasks
    loop-engineering chief-of-staff brief morning|midday|evening
    loop-engineering chief-of-staff schedule
    loop-engineering chief-of-staff approve-schedule
    loop-engineering chief-of-staff execute-safe
    loop-engineering chief-of-staff checkpoint
    loop-engineering chief-of-staff dashboard
    loop-engineering chief-of-staff status

The ``--demo`` flag (default when no ``--data`` given) runs against the
committed synthetic demo. Real runs point ``--data`` at a private import dir.
Clocks are fixed via ``--day``/``--as-of``/``--run-id`` so output is
reproducible; a real invocation supplies them from run metadata.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
    FixtureCalendarAdapter,
    FixtureSourceAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.adapters.google_calendar import (
    GoogleCalendarAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.dashboard import render_dashboard
from loop_engineering.use_cases.personal_chief_of_staff.execute import (
    approve_and_create_focus_blocks,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import AdapterMode
from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path
from loop_engineering.use_cases.personal_chief_of_staff.runner import (
    ChiefOfStaff,
    RunResult,
    load_latest_checkpoint,
    write_private,
)
from loop_engineering.use_cases.personal_chief_of_staff.store import RegisterStore

DEMO_DIR = Path("use_cases/personal-chief-of-staff/demo")
SOURCE_NAMES = ("email", "github", "drive", "chat_context", "manual")


def _calendar_adapter(args: argparse.Namespace, data_dir: Path, mode: AdapterMode):  # type: ignore[no-untyped-def]
    """Choose the calendar source honestly.

    'fixture' → the fixture adapter (labeled FIXTURE). 'live' → the Google
    adapter, whose failures surface loudly. 'auto' → live ONLY when
    credentials are present and usable; otherwise fixture — the choice is
    what the status/mode labels report, never a silent LIVE claim.
    """
    choice = getattr(args, "calendar", "auto")
    if choice == "fixture":
        return FixtureCalendarAdapter(data_dir, mode=mode)
    google = GoogleCalendarAdapter(now_iso=args.as_of)
    if choice == "live":
        return google
    return (
        google if google.status()["authenticated"] else FixtureCalendarAdapter(data_dir, mode=mode)
    )


def _build(
    data_dir: Path, mode: AdapterMode, args: argparse.Namespace | None = None
) -> ChiefOfStaff:
    sources = [FixtureSourceAdapter(name, data_dir, mode=mode) for name in SOURCE_NAMES]
    if args is None:
        calendar = FixtureCalendarAdapter(data_dir, mode=mode)
    else:
        calendar = _calendar_adapter(args, data_dir, mode)
    return ChiefOfStaff(sources, calendar)


def _run(args: argparse.Namespace) -> RunResult:
    data_dir = Path(args.data) if args.data else DEMO_DIR
    mode = AdapterMode.MANUAL_IMPORT if args.data else AdapterMode.FIXTURE
    cos = _build(data_dir, mode, args)
    # Prior decision context feeds drift protection: past prohibited actions
    # must not reappear as next steps (review finding #3).
    prior = load_latest_checkpoint()
    # Cross-run persistence: the append-only private journal is the register
    # of record; statuses, decisions, and artifacts survive between runs.
    store = None if args.no_persist else RegisterStore()
    return cos.run(
        run_id=args.run_id,
        day=args.day,
        as_of=args.as_of,
        prior_checkpoint=prior,
        store=store,
    )


def cmd(args: argparse.Namespace) -> int:
    sub = args.cos_command
    if sub == "status":
        cos = _build(Path(args.data) if args.data else DEMO_DIR, AdapterMode.FIXTURE, args)
        print("Chief of Staff — adapter status")
        for row in cos.adapter_status():
            print(f"  [{row['mode']:<13}] {row['name']}")
            if row["mode"] in ("UNAVAILABLE", "MANUAL_IMPORT"):
                print(f"      setup: {row['setup']}")
        google = GoogleCalendarAdapter(now_iso=args.as_of)
        st = google.status()
        print("Google Calendar (live, read-only):")
        print(f"  mode: {st['mode']} · auth: {st['auth_state']}")
        print(
            f"  last successful read: {st['last_read_at'] or '(never this session)'} · "
            f"calendars: {st['calendars_read']} · events: {st['events_read']}"
        )
        if st["remediation"]:
            print(f"  remediation: {st['remediation']}")
        return 0

    if sub == "check-calendar":
        google = GoogleCalendarAdapter(now_iso=args.as_of)
        if not google.status()["authenticated"]:
            print("Google Calendar: UNAVAILABLE (not configured) — read-only check skipped")
            print(f"  remediation: {google.setup_instructions()}")
            return 0
        report = google.connection_check()
        if report["ok"]:
            print(
                f"Google Calendar: LIVE — read {report['events_read']} event(s) "
                f"at {report['last_read_at']} (read-only)"
            )
            return 0
        print(f"Google Calendar: check FAILED — {report['error']}")
        print(f"  remediation: {report['remediation']}")
        return 1

    result = _run(args)

    if sub == "ingest":
        out = write_private(result)
        print(f"ingested {len(result.register.tasks)} tasks → {out} (private, gitignored)")
        return 0
    if sub == "tasks":
        for st in result.scored:
            t = st.task
            src = t.sources[0]
            print(
                f"[{st.score:6.1f}] {t.title[:56]:<56} "
                f"{'INF' if t.is_inferred else 'EXP'} {t.confidence:.2f} "
                f"{src.source_type.value}:{src.source_reference}"
            )
        return 0
    if sub == "brief":
        print(result.briefs[args.when], end="")
        return 0
    if sub == "schedule":
        print(f"Proposed schedule for {result.day} ({result.schedule.free_minutes} min free):")
        for b in result.schedule.blocks:
            print(f"  {b.start} → {b.end}  [Focus] {b.title}")
        if result.schedule.overflow:
            print(f"  overflow (did not fit): {', '.join(result.schedule.overflow)}")
        print(f"  note: {result.schedule.note}")
        print("  → run 'approve-schedule' to create these focus blocks (one approval).")
        return 0
    if sub == "approve-schedule":
        data_dir = Path(args.data) if args.data else DEMO_DIR
        calendar = FixtureCalendarAdapter(data_dir)
        created = approve_and_create_focus_blocks(result.schedule, calendar, approved=True)
        print(f"approved — created {len(created)} focus block(s): {', '.join(created)}")
        return 0
    if sub == "execute-safe":
        r = result.safe_result
        print(f"executed {len(r.executed)} safe action(s):")
        for a in r.executed:
            print(f"  ✓ {a.action_type} → {a.target}")
        if r.blocked:
            print(f"blocked (need explicit approval) — {len(r.blocked)}:")
            for a in r.blocked:
                print(f"  ✗ {a.action_type} → {a.target}")
        return 0
    if sub == "checkpoint":
        cp = result.checkpoint
        out = private_path(f"runs/private/cos/{result.run_id}/checkpoint.json")
        import json

        payload = json.dumps(cp.to_dict(), indent=2, sort_keys=True)
        out.write_text(payload, encoding="utf-8")
        # Refresh the stable prior-context file the next run loads.
        from loop_engineering.use_cases.personal_chief_of_staff.runner import (
            LATEST_CHECKPOINT,
        )

        private_path(LATEST_CHECKPOINT).write_text(payload, encoding="utf-8")
        print(f"checkpoint written → {out} (private)")
        print(f"  digest: {cp.context_digest}")
        return 0
    if sub == "dashboard":
        html = render_dashboard(result)
        out = private_path(f"runs/private/cos/{result.run_id}/dashboard.html")
        out.write_text(html, encoding="utf-8")
        print(f"dashboard → {out}")
        print(f"  open: file://{out}")
        return 0
    print(f"unknown chief-of-staff command: {sub}")
    return 2


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("cos_command")
    p.add_argument("when", nargs="?", default="morning", help="for 'brief': morning|midday|evening")
    p.add_argument("--data", default=None, help="private import dir (default: synthetic demo)")
    p.add_argument(
        "--calendar",
        choices=("auto", "live", "fixture"),
        default="auto",
        help="calendar source: auto = live when configured, else fixture (labeled honestly)",
    )
    p.add_argument(
        "--no-persist",
        dest="no_persist",
        action="store_true",
        help="stateless run: skip the private cross-run register journal",
    )
    p.add_argument("--day", default="2026-07-17")
    p.add_argument("--as-of", dest="as_of", default="2026-07-17T08:00:00+00:00")
    p.add_argument("--run-id", dest="run_id", default="cos-demo")
