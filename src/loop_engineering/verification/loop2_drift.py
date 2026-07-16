"""Loop 2 — Plan and Goal-Drift Verification (spec §6).

Runs after every workstream/stage and after any plan change. Confirms the plan
still serves the locked goal, nothing important is uncovered, no unnecessary
work crept in, and drift stays below the 5% guardrail (PD-04).
"""

from __future__ import annotations

import uuid
from typing import Any

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.models import CheckResult, Task, VerificationResult, utc_now
from loop_engineering.planning.planner import PlanChange, coverage

DRIFT_LIMIT_PCT = 5.0
VERIFIER_ROLE = "goal-drift-reviewer"


def verify_plan(
    contract: dict[str, Any],
    tasks: list[Task],
    plan_changes: list[PlanChange] | None = None,
    stage: str = "stage",
) -> VerificationResult:
    goal_contract.verify_integrity(contract)
    report = coverage(contract, tasks)
    changes = plan_changes or []
    checks = [
        CheckResult(
            "tasks_serve_locked_goal",
            not report.orphan_task_ids,
            f"orphan tasks (no contract requirement): {report.orphan_task_ids}"
            if report.orphan_task_ids
            else "every task maps to a contract requirement",
        ),
        CheckResult(
            "no_uncovered_goal_elements",
            not report.uncovered_requirements,
            f"uncovered requirements: {report.uncovered_requirements}"
            if report.uncovered_requirements
            else "every requirement has at least one task",
        ),
        CheckResult(
            "plan_changes_have_reasons",
            all(c.reason.strip() and c.evidence.strip() for c in changes),
            f"{len(changes)} plan change(s) recorded",
        ),
        CheckResult(
            "drift_below_limit",
            report.drift_pct < DRIFT_LIMIT_PCT,
            f"drift {report.drift_pct}% (limit {DRIFT_LIMIT_PCT}%)",
        ),
    ]
    passed = all(c.passed for c in checks)
    return VerificationResult(
        verification_id=f"v2-{stage}-{uuid.uuid4().hex[:8]}",
        loop="loop2_drift",
        subject_id=stage,
        verifier_role=VERIFIER_ROLE,
        passed=passed,
        checks=checks,
        failure_reason=None
        if passed
        else "; ".join(f"{c.name}: {c.detail}" for c in checks if not c.passed),
        verified_at=utc_now(),
    )
