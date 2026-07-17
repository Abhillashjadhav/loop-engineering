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
from loop_engineering.use_cases.personal_chief_of_staff.dashboard import render_dashboard
from loop_engineering.use_cases.personal_chief_of_staff.execute import (
    approve_and_create_focus_blocks,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import AdapterMode
from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path
from loop_engineering.use_cases.personal_chief_of_staff.runner import (
    ChiefOfStaff,
    RunResult,
    write_private,
)

DEMO_DIR = Path("use_cases/personal-chief-of-staff/demo")
SOURCE_NAMES = ("email", "github", "drive", "chat_context", "manual")


def _build(data_dir: Path, mode: AdapterMode) -> ChiefOfStaff:
    sources = [FixtureSourceAdapter(name, data_dir, mode=mode) for name in SOURCE_NAMES]
    calendar = FixtureCalendarAdapter(data_dir, mode=mode)
    return ChiefOfStaff(sources, calendar)


def _run(args: argparse.Namespace) -> RunResult:
    data_dir = Path(args.data) if args.data else DEMO_DIR
    mode = AdapterMode.MANUAL_IMPORT if args.data else AdapterMode.FIXTURE
    cos = _build(data_dir, mode)
    return cos.run(run_id=args.run_id, day=args.day, as_of=args.as_of)


def cmd(args: argparse.Namespace) -> int:
    sub = args.cos_command
    if sub == "status":
        cos = _build(Path(args.data) if args.data else DEMO_DIR, AdapterMode.FIXTURE)
        print("Chief of Staff — adapter status")
        for row in cos.adapter_status():
            print(f"  [{row['mode']:<13}] {row['name']}")
            if row["mode"] in ("UNAVAILABLE", "MANUAL_IMPORT"):
                print(f"      setup: {row['setup']}")
        return 0

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

        out.write_text(json.dumps(cp.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
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
    p.add_argument("--day", default="2026-07-17")
    p.add_argument("--as-of", dest="as_of", default="2026-07-17T08:00:00+00:00")
    p.add_argument("--run-id", dest="run_id", default="cos-demo")
