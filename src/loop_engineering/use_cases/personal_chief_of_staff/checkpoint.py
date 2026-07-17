"""Context-drift protection + decision checkpoints.

Before any brief/recommendation/action, ``drift_check`` verifies alignment
against the locked Operating Contract: goal alignment, scope, decision
consistency, terminology, evidence (every task has a source), uncertainty
that has silently become fact, and a lower-priority task displacing a locked
priority. A prohibited-action violation blocks regardless of score. A compact
DecisionCheckpoint is written after each evening close and material decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    DecisionCheckpoint,
    Task,
)
from loop_engineering.use_cases.personal_chief_of_staff.prioritize import ScoredTask


@dataclass
class DriftReport:
    ok: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "violations": list(self.violations), "warnings": list(self.warnings)}


def drift_check(
    scored: list[ScoredTask],
    contract: OperatingContract,
    prior: DecisionCheckpoint | None = None,
) -> DriftReport:
    """Return a DriftReport. ``ok`` is False if any hard violation is present."""
    violations: list[str] = []
    warnings: list[str] = []
    rejected = {r.lower() for r in contract.rejected_ideas}

    for st in scored:
        task = st.task
        # Evidence consistency: every task must carry a source.
        if not task.sources:
            violations.append(f"task {task.id!r} has no source (evidence guard)")
        # Uncertainty silently became fact: inferred + high stated confidence
        # but no explicit origin anywhere is a drift smell.
        if task.is_inferred and task.confidence >= 0.9:
            warnings.append(
                f"task {task.id!r} is inferred yet scored at high confidence — verify before acting"
            )
        # Goal alignment: a scored top task with no goal link is a scope warning.
        if not task.goal_ids and st.category not in ("admin", "blocked_or_waiting"):
            warnings.append(f"task {task.id!r} is not linked to any locked goal (scope)")
        # Rejected idea resurfacing as approved work.
        blob = f"{task.title} {task.description} {task.project}".lower()
        for r in rejected:
            if r and r in blob:
                violations.append(
                    f"task {task.id!r} matches a rejected idea ({r!r}) — must not resurface as work"
                )
        # Prior prohibited actions must never reappear as next steps.
    if prior:
        for prohibited in prior.prohibited_actions:
            for st in scored:
                if prohibited.lower() in f"{st.task.title}".lower():
                    violations.append(
                        f"task {st.task.id!r} revisits a prohibited action {prohibited!r}"
                    )

    # Priority displacement: a locked top-priority category (external/job) must
    # not be outranked by admin. If any admin task scores above any job/external
    # task, that is displacement drift.
    top_cats = {"external_commitment", "job_search"}
    admin_scores = [st.score for st in scored if st.category == "admin"]
    top_scores = [st.score for st in scored if st.category in top_cats]
    if admin_scores and top_scores and max(admin_scores) > min(top_scores):
        violations.append(
            "priority displacement: an administration task outranks a locked "
            "job-search/external-commitment task"
        )

    return DriftReport(ok=not violations, violations=violations, warnings=warnings)


def build_checkpoint(
    now_iso: str,
    scored: list[ScoredTask],
    contract: OperatingContract,
    approved_decisions: list[str] | None = None,
    rejected: list[str] | None = None,
    open_questions: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> DecisionCheckpoint:
    """Compact, source-anchored context digest for the next run."""
    top = [st.task.title for st in scored[:3]]
    digest = (
        f"{len(scored)} tasks tracked; top: {'; '.join(top) or '(none)'}. "
        f"Goals G1-G{len(contract.goals)} active. "
        f"Prohibited actions enforced: {len(contract.prohibited_actions)}."
    )
    return DecisionCheckpoint(
        timestamp=now_iso,
        approved_decisions=list(approved_decisions or contract.decisions),
        rejected_ideas=list(rejected or contract.rejected_ideas),
        open_questions=list(open_questions or contract.open_questions),
        prohibited_actions=list(contract.prohibited_actions),
        next_steps=list(next_steps or [st.task.title for st in scored[:1]]),
        context_digest=digest,
    )


def carried_forward(scored: list[ScoredTask], done_ids: set[str]) -> list[Task]:
    """Tasks that were not completed — the north-star guard: nothing important
    silently disappears between ingestion and the brief."""
    return [st.task for st in scored if st.task.id not in done_ids]
