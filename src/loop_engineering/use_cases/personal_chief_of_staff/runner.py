"""Chief of Staff orchestrator.

Wires adapters → discovery → register → prioritize → drift-check → schedule →
safe actions → briefs → checkpoint → dashboard. Deterministic: all clocks are
inputs (``as_of``, ``day``, ``run_id``), never ``datetime.now()``. Generated
personal content is written only under ``runs/private/`` via the privacy guard.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loop_engineering.use_cases.personal_chief_of_staff import briefs as briefs_mod
from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import (
    CalendarAdapter,
    SourceAdapter,
)
from loop_engineering.use_cases.personal_chief_of_staff.checkpoint import (
    build_checkpoint,
    drift_check,
)
from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.discovery import discover
from loop_engineering.use_cases.personal_chief_of_staff.execute import (
    execute_safe,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    ActionProposal,
    ApprovalRequirement,
    DecisionCheckpoint,
    Task,
    TaskStatus,
)
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import prioritize
from loop_engineering.use_cases.personal_chief_of_staff.registry import TaskRegister
from loop_engineering.use_cases.personal_chief_of_staff.schedule import propose_schedule

if TYPE_CHECKING:
    from loop_engineering.use_cases.personal_chief_of_staff.store import RegisterStore


def _safe_proposals_for(tasks: list[Task]) -> list[ActionProposal]:
    """Derive safe (auto-executable) action proposals from the register."""
    props: list[ActionProposal] = []
    for t in tasks[:12]:
        title = t.title.lower()
        if t.waiting_on:
            props.append(
                ActionProposal(
                    id=f"a-wait-{t.id}",
                    action_type="waiting_on_followup_draft",
                    target=t.waiting_on,
                    reason=f"waiting on {t.waiting_on} for: {t.title}",
                    expected_result="draft follow-up saved (not sent)",
                    risk="low",
                    approval_requirement=ApprovalRequirement.NONE,
                )
            )
        if "interview" in title or "prepare" in title:
            props.append(
                ActionProposal(
                    id=f"a-prep-{t.id}",
                    action_type="interview_prep_session",
                    target=t.id,
                    reason="upcoming interview needs preparation",
                    expected_result="interview practice session generated",
                    risk="low",
                    approval_requirement=ApprovalRequirement.NONE,
                )
            )
        if t.project or "review" in title:
            props.append(
                ActionProposal(
                    id=f"a-issue-{t.id}",
                    action_type="github_issue_proposal",
                    target=t.project or t.id,
                    reason=f"track work: {t.title}",
                    expected_result="draft GitHub issue/checklist (not created)",
                    risk="low",
                    approval_requirement=ApprovalRequirement.NONE,
                )
            )
    return props


@dataclass
class RunResult:
    run_id: str
    day: str
    as_of: str
    register: TaskRegister
    scored: list[Any]
    schedule: Any
    drift: Any
    safe_result: Any
    checkpoint: Any
    contract: OperatingContract
    briefs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "day": self.day,
            "as_of": self.as_of,
            "register": self.register.to_dict(),
            "scored": [s.to_dict() for s in self.scored],
            "schedule": self.schedule.to_dict(),
            "drift": self.drift.to_dict(),
            "safe_execution": self.safe_result.to_dict(),
            "checkpoint": self.checkpoint.to_dict(),
        }


class ChiefOfStaff:
    def __init__(
        self,
        source_adapters: Sequence[SourceAdapter],
        calendar: CalendarAdapter,
        contract: OperatingContract | None = None,
    ) -> None:
        self.sources = list(source_adapters)
        self.calendar = calendar
        self.contract = contract or OperatingContract()

    def adapter_status(self) -> list[dict[str, str]]:
        rows = [
            {"name": a.name, "mode": a.mode.value, "setup": a.setup_instructions()}
            for a in self.sources
        ]
        rows.append(
            {
                "name": self.calendar.name,
                "mode": self.calendar.mode.value,
                "setup": self.calendar.setup_instructions(),
            }
        )
        return rows

    def run(
        self,
        run_id: str,
        day: str,
        as_of: str,
        prior_checkpoint: DecisionCheckpoint | None = None,
        store: RegisterStore | None = None,
    ) -> RunResult:
        # 1. ingest + discover
        raw = [item for a in self.sources for item in a.fetch()]
        tasks = discover(raw, as_of)
        # 1b. cross-run persistence: observations land in the append-only
        #     private journal (idempotent), and the working set becomes the
        #     PERSISTED register view — statuses, decisions, and provenance
        #     recorded in earlier runs survive into this one.
        if store is not None:
            store.ingest(tasks, as_of)
            if prior_checkpoint is None:
                history = store.checkpoints()
                prior_checkpoint = history[-1] if history else None
            tasks = store.view()
        # 2. consolidate (dedup preserving provenance)
        register = TaskRegister(tasks)
        # link goals deterministically by keyword (kept simple + auditable)
        _link_goals(register.tasks, self.contract)
        # 3. prioritize
        scored = prioritize(register.tasks, self.contract, day)
        # 4. drift check (context-drift protection) against the PRIOR
        #    checkpoint too, so past prohibited decisions cannot silently
        #    reappear as next steps (review finding #3).
        drift = drift_check(scored, self.contract, prior=prior_checkpoint)
        # 5. schedule (real free time only) — only actionable work is packed;
        #    blocked/waiting/inbox/done tasks never consume focus blocks.
        events = self.calendar.events()
        schedulable = [st for st in scored if st.task.status is TaskStatus.ACTIVE]
        schedule = propose_schedule(schedulable, events, day)
        # 6. safe actions (fail-closed gate)
        proposals = _safe_proposals_for(register.tasks)
        safe_result = execute_safe(proposals, self.contract)
        # 7. checkpoint
        checkpoint = build_checkpoint(as_of, scored, self.contract)
        if store is not None:
            # Checkpoint history + generated artifacts survive across runs.
            store.append_checkpoint(checkpoint, at=as_of)
            for executed in safe_result.executed:
                store.append_artifact(executed.to_dict(), at=as_of)
        # 8. briefs
        overdue = register.overdue(day)
        blocked = register.blocked()
        waiting = register.waiting()
        safe_titles = [f"{a.action_type} → {a.target}" for a in safe_result.executed]
        completed = [t for t in register.tasks if t.status is TaskStatus.DONE]
        incomplete = [t for t in register.tasks if t.status is not TaskStatus.DONE]
        b = {
            "morning": briefs_mod.morning_brief(
                run_id,
                as_of,
                day,
                scored,
                events,
                overdue,
                blocked,
                schedule,
                safe_titles,
                drift,
            ),
            "midday": briefs_mod.midday_check(
                run_id,
                as_of,
                day,
                completed,
                [],
                [],
                waiting,
                schedule.note,
            ),
            "evening": briefs_mod.evening_close(
                run_id,
                as_of,
                day,
                completed,
                incomplete,
                incomplete,
                waiting,
                scored[0].task if scored else None,
                checkpoint.context_digest,
                [f"{t.title} ({t.confidence:.2f})" for t in register.inbox()],
            ),
        }
        return RunResult(
            run_id=run_id,
            day=day,
            as_of=as_of,
            register=register,
            scored=scored,
            schedule=schedule,
            drift=drift,
            safe_result=safe_result,
            checkpoint=checkpoint,
            contract=self.contract,
            briefs=b,
        )


def _link_goals(tasks: list[Task], contract: OperatingContract) -> None:
    keymap = {
        "G1": ("interview", "recruiter", "application", "job", "offer", "role"),
        "G2": ("peos", "production engineering", "pm-evals"),
        "G3": ("package", "complete", "ship", "product"),
        "G4": ("authority", "distribution", "blog", "post"),
        "G5": ("conference", "podcast", "talk", "speaking", "cfp"),
        "G7": ("health", "personal", "dentist", "family"),
    }
    for t in tasks:
        blob = f"{t.title} {t.description} {t.project}".lower()
        linked = sorted({g for g, kws in keymap.items() if any(k in blob for k in kws)})
        if linked:
            t.goal_ids = linked


LATEST_CHECKPOINT = "runs/private/cos/checkpoint-latest.json"


def write_private(result: RunResult, root: Path | None = None) -> Path:
    """Write briefs + run JSON under runs/private/ (gitignored). Returns dir.

    Also refreshes the stable ``checkpoint-latest.json`` so the NEXT run can
    load it as its prior decision context (review finding #3)."""
    from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path

    base = f"runs/private/cos/{result.run_id}"
    out = private_path(f"{base}/run.json", root=root)
    out.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    for name, text in result.briefs.items():
        bp = private_path(f"{base}/brief-{name}.md", root=root)
        bp.write_text(text, encoding="utf-8")
    latest = private_path(LATEST_CHECKPOINT, root=root)
    latest.write_text(
        json.dumps(result.checkpoint.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return out.parent


def load_latest_checkpoint(root: Path | None = None) -> DecisionCheckpoint | None:
    """Load the persisted prior checkpoint, or None when none exists yet."""
    from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path

    try:
        path = private_path(LATEST_CHECKPOINT, root=root, ensure_parent=False)
    except Exception:
        return None
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return DecisionCheckpoint(
        timestamp=str(data.get("timestamp", "")),
        approved_decisions=[str(x) for x in data.get("approved_decisions", [])],
        rejected_ideas=[str(x) for x in data.get("rejected_ideas", [])],
        open_questions=[str(x) for x in data.get("open_questions", [])],
        prohibited_actions=[str(x) for x in data.get("prohibited_actions", [])],
        next_steps=[str(x) for x in data.get("next_steps", [])],
        context_digest=str(data.get("context_digest", "")),
    )
