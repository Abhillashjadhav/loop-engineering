"""Plan construction and goal-drift measurement (spec §6 Loop 2 support).

A plan is a dependency-ordered list of atomic tasks. Use-case modules build
plans; this module owns the goal-alignment math so drift is measured the same
way everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import ContractViolation
from loop_engineering.domain.models import Task, TaskStatus


@dataclass
class PlanChange:
    """A recorded, evidence-backed plan change. Never silently rewrite history."""

    changed_at: str
    reason: str
    evidence: str
    added_task_ids: list[str] = field(default_factory=list)
    removed_task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_at": self.changed_at,
            "reason": self.reason,
            "evidence": self.evidence,
            "added_task_ids": list(self.added_task_ids),
            "removed_task_ids": list(self.removed_task_ids),
        }


@dataclass
class CoverageReport:
    """How well the plan covers the contract, and vice versa."""

    covered_requirements: list[str]
    uncovered_requirements: list[str]
    orphan_task_ids: list[str]
    drift_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "covered_requirements": list(self.covered_requirements),
            "uncovered_requirements": list(self.uncovered_requirements),
            "orphan_task_ids": list(self.orphan_task_ids),
            "drift_pct": self.drift_pct,
        }


def validate_plan(contract: dict[str, Any], tasks: list[Task]) -> None:
    """Structural plan validation: unique ids, resolvable deps, no cycles."""
    ids = [t.task_id for t in tasks]
    if len(ids) != len(set(ids)):
        raise ContractViolation("plan contains duplicate task ids")
    known = set(ids)
    for t in tasks:
        missing = [d for d in t.dependencies if d not in known]
        if missing:
            raise ContractViolation(f"task {t.task_id} depends on unknown tasks {missing}")
    _assert_acyclic(tasks)


def _assert_acyclic(tasks: list[Task]) -> None:
    deps = {t.task_id: set(t.dependencies) for t in tasks}
    resolved: set[str] = set()
    while deps:
        ready = [tid for tid, d in deps.items() if d <= resolved]
        if not ready:
            raise ContractViolation(f"plan has a dependency cycle among {sorted(deps)}")
        for tid in ready:
            resolved.add(tid)
            del deps[tid]


def coverage(contract: dict[str, Any], tasks: list[Task]) -> CoverageReport:
    """Compute requirement coverage and the goal-drift percentage.

    Drift counts two symmetric failure modes:
    - orphan tasks: tasks whose goal_requirement is not in the contract
      (silent scope expansion);
    - uncovered requirements: contract requirements no task serves
      (silent scope loss).

    drift_pct = (orphans + uncovered) / (len(tasks) + len(requirements)) * 100.
    The PD-04 guardrail requires drift_pct < 5.
    """
    reqs = goal_contract.requirements(contract)
    req_set = set(reqs)
    active = [t for t in tasks if t.status != TaskStatus.SKIPPED_WITH_REASON]
    served = {t.goal_requirement for t in active}
    orphans = [t.task_id for t in active if t.goal_requirement not in req_set]
    uncovered = [r for r in reqs if r not in served]
    covered = [r for r in reqs if r in served]
    denominator = len(active) + len(reqs)
    drift = 0.0 if denominator == 0 else (len(orphans) + len(uncovered)) / denominator * 100.0
    return CoverageReport(
        covered_requirements=covered,
        uncovered_requirements=uncovered,
        orphan_task_ids=orphans,
        drift_pct=round(drift, 2),
    )


def execution_order(tasks: list[Task]) -> list[Task]:
    """Deterministic topological order (dependency-first, then task_id)."""
    by_id = {t.task_id: t for t in tasks}
    resolved: list[str] = []
    resolved_set: set[str] = set()
    remaining = dict.fromkeys(sorted(by_id))
    while remaining:
        progressed = False
        for tid in list(remaining):
            if set(by_id[tid].dependencies) <= resolved_set:
                resolved.append(tid)
                resolved_set.add(tid)
                del remaining[tid]
                progressed = True
        if not progressed:
            raise ContractViolation(f"cannot order plan; cycle among {sorted(remaining)}")
    return [by_id[tid] for tid in resolved]
