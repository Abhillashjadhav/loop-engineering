"""loop-engineering CLI (spec §12).

Commands: init, plan, run, resume, status, verify, report, audit-github.
The /loop-engineer skill orchestrates; this CLI (deterministic Python) owns
state, policies, schemas, verification bookkeeping, budgets, recovery, and
reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import LoopEngineeringError
from loop_engineering.domain.models import TaskStatus
from loop_engineering.runtime.engine import Engine
from loop_engineering.runtime.ledger import RunLedger
from loop_engineering.runtime.state import load_state
from loop_engineering.use_cases.github_authority_audit.datasource import (
    FixtureDataSource,
    GitHubDataSource,
    LiveDataSource,
)
from loop_engineering.use_cases.github_authority_audit.runner import AuditUseCase
from loop_engineering.use_cases.personal_chief_of_staff import cli as cos_cli
from loop_engineering.verification import e2e_reviewer

CONTRACTS_DIR = Path("contracts")


def _load_subjects(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    subjects = data.get("subjects", []) if isinstance(data, dict) else []
    if not subjects:
        raise LoopEngineeringError(f"no subjects found in {path}")
    return [dict(s) for s in subjects]


def _data_source(args: argparse.Namespace) -> GitHubDataSource:
    if getattr(args, "fixtures", None):
        return FixtureDataSource(args.fixtures)
    return LiveDataSource()


def _use_case(args: argparse.Namespace) -> AuditUseCase:
    return AuditUseCase(_data_source(args), _load_subjects(args.subjects))


def _resolve_run_dir(run_ref: str, runs_root: str) -> Path:
    direct = Path(run_ref)
    if (direct / "state.json").is_file():
        return direct
    root = Path(runs_root)
    matches = list(root.glob(f"*/{run_ref}")) if root.exists() else []
    if len(matches) == 1:
        return matches[0]
    raise LoopEngineeringError(
        f"cannot resolve run {run_ref!r}: pass a run directory path or a run id "
        f"unique under {runs_root}/<goal-id>/"
    )


def cmd_init(args: argparse.Namespace) -> int:
    draft = goal_contract.load_unlocked(args.goal_file)
    locked = goal_contract.lock(draft)
    out = Path(args.out) if args.out else CONTRACTS_DIR / f"{locked['goal_id']}.locked.yaml"
    goal_contract.save(locked, out)
    print(f"locked contract written: {out}")
    print(f"goal_id: {locked['goal_id']} v{locked['version']}")
    print(f"digest:  {locked['canonical_digest']}")
    return 0


def _contract_for(goal_id: str, contracts_dir: str) -> dict[str, Any]:
    path = Path(contracts_dir) / f"{goal_id}.locked.yaml"
    if not path.is_file():
        raise LoopEngineeringError(
            f"no locked contract at {path}; run `loop-engineering init <goal.yaml>` first"
        )
    return goal_contract.load(path)


def cmd_plan(args: argparse.Namespace) -> int:
    contract = _contract_for(args.goal_id, args.contracts_dir)
    use_case = _use_case(args)
    tasks = use_case.build_plan(contract, {})
    print(f"plan for {contract['goal_id']} ({len(tasks)} atomic tasks):")
    for t in tasks:
        deps = f"  <- {','.join(t.dependencies)}" if t.dependencies else ""
        print(f"  {t.task_id}: {t.action}{deps}")
    print("\napprove the goal contract once; the run then continues autonomously.")
    return 0


def _run_engine(engine: Engine, interrupt_after: int | None = None) -> int:
    result = engine.run(interrupt_after=interrupt_after)
    state = result.state
    print(f"run {state.run_id}: {state.status.value}")
    if result.gate_a and result.gate_b:
        print(f"gate A: {result.gate_a.verdict.value}")
        print(f"gate B: {result.gate_b.score}/100 -> {result.gate_b.verdict.value}")
    if result.pack_dir:
        print(f"accuracy evidence pack: {result.pack_dir}")
        return 0
    print("run did not produce a deliverable success; see reports/ in the run directory")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    contract = _contract_for(args.goal_id, args.contracts_dir)
    engine = Engine(
        contract,
        _use_case(args),
        runs_root=args.runs_root,
        config={"outputs_root": args.outputs_root},
    )
    print(f"run directory: {engine.run_directory}")
    return _run_engine(engine, args.interrupt_after)


def cmd_resume(args: argparse.Namespace) -> int:
    run_directory = _resolve_run_dir(args.run_id, args.runs_root)
    engine = Engine.resume(
        run_directory, _use_case(args), config={"outputs_root": args.outputs_root}
    )
    print(f"resuming run: {run_directory}")
    return _run_engine(engine)


def cmd_status(args: argparse.Namespace) -> int:
    run_directory = _resolve_run_dir(args.run_id, args.runs_root)
    state = load_state(run_directory)
    print(json.dumps(state.to_dict(), indent=2))
    ledger = RunLedger(run_directory)
    transitions = ledger.transitions()
    statuses: dict[str, str] = {}
    for t in transitions:
        statuses[str(t["task_id"])] = str(t["to"])
    if statuses:
        print("\ntasks:")
        for task_id, status in sorted(statuses.items()):
            print(f"  {task_id}: {status}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Read-only re-verification: recompute Gate A from persisted records."""
    run_directory = _resolve_run_dir(args.run_id, args.runs_root)
    state = load_state(run_directory)
    from loop_engineering.runtime.checkpoint import (
        latest_checkpoint,
        load_tasks_from_checkpoint,
    )

    checkpoint = latest_checkpoint(run_directory)
    if checkpoint is None:
        print("no checkpoint found; nothing to verify", file=sys.stderr)
        return 1
    tasks = load_tasks_from_checkpoint(checkpoint)
    engine_records = Engine.__new__(Engine)
    engine_records.run_directory = run_directory
    verifications = engine_records._load_verifications()
    contract = goal_contract.load(run_directory / "contract.yaml")
    stability_required = int(contract.get("replication_count", 1)) >= 6
    gate_a = e2e_reviewer.review_process(
        state, tasks, verifications, run_directory, stability_required
    )
    print(f"gate A (read-only): {gate_a.verdict.value}")
    for c in gate_a.checks:
        print(
            f"  {'PASS' if c.passed else 'FAIL'} {c.name}" + (f" — {c.detail}" if c.detail else "")
        )
    verified = sum(1 for t in tasks if t.status == TaskStatus.VERIFIED)
    print(f"tasks verified: {verified}/{len(tasks)}")
    return 0 if gate_a.verdict.value == "COMPLETE" else 1


def cmd_report(args: argparse.Namespace) -> int:
    run_directory = _resolve_run_dir(args.run_id, args.runs_root)
    state = load_state(run_directory)
    pack = Path(args.outputs_root) / state.goal_id
    print(f"run:    {run_directory} ({state.status.value})")
    if (pack / "accuracy-evidence.md").is_file():
        print(f"pack:   {pack}")
        print((pack / "accuracy-evidence.md").read_text(encoding="utf-8"))
        return 0
    blocked = run_directory / "reports" / "BLOCKED.md"
    if blocked.is_file():
        print(blocked.read_text(encoding="utf-8"))
    else:
        print("no evidence pack and no blocking report — run may be in progress")
    return 1


def cmd_audit_github(args: argparse.Namespace) -> int:
    """One-shot audit: lock the matching contract and run it."""
    goal_file = args.goal_file or (
        "examples/goal.synthetic.yaml" if args.fixtures else "examples/goal.yaml"
    )
    draft = goal_contract.load_unlocked(goal_file)
    contract = goal_contract.lock(draft)
    goal_contract.save(contract, Path(args.contracts_dir) / f"{contract['goal_id']}.locked.yaml")
    engine = Engine(
        contract,
        _use_case(args),
        runs_root=args.runs_root,
        config={"outputs_root": args.outputs_root},
    )
    print(f"run directory: {engine.run_directory}")
    return _run_engine(engine, args.interrupt_after)


def _add_common(p: argparse.ArgumentParser, subjects: bool = True) -> None:
    p.add_argument("--runs-root", default="runs")
    p.add_argument("--outputs-root", default="outputs")
    p.add_argument("--contracts-dir", default=str(CONTRACTS_DIR))
    if subjects:
        p.add_argument("--subjects", default="examples/subjects.synthetic.yaml")
        p.add_argument(
            "--fixtures",
            default=None,
            help="fixture snapshot directory (offline mode); omit for --live",
        )
        p.add_argument(
            "--live",
            action="store_true",
            help="use the live data source (fails loudly when unavailable)",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-engineering",
        description="Self-verifying autonomous goal loop.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="lock a draft goal contract (digest + schema)")
    p.add_argument("goal_file")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="show the atomic task plan for a locked goal")
    p.add_argument("goal_id")
    _add_common(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("run", help="run a locked goal end to end")
    p.add_argument("goal_id")
    p.add_argument("--interrupt-after", type=int, default=None, help=argparse.SUPPRESS)
    _add_common(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("resume", help="resume an interrupted run")
    p.add_argument("run_id")
    _add_common(p)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("status", help="show run state and task statuses")
    p.add_argument("run_id")
    _add_common(p, subjects=False)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("verify", help="read-only process-completeness verification")
    p.add_argument("run_id")
    _add_common(p, subjects=False)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("report", help="print the accuracy evidence or blocking report")
    p.add_argument("run_id")
    _add_common(p, subjects=False)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("audit-github", help="one-shot GitHub authority audit")
    p.add_argument("--goal-file", default=None)
    p.add_argument("--interrupt-after", type=int, default=None, help=argparse.SUPPRESS)
    _add_common(p)
    p.set_defaults(func=cmd_audit_github)

    p = sub.add_parser("chief-of-staff", help="personal chief of staff (private use case)")
    cos_cli.add_arguments(p)
    p.set_defaults(func=lambda a: cos_cli.cmd(a))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
    except LoopEngineeringError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
