"""North Star + leading metrics (PD-02, PD-03).

The North Star is human_active_minutes_saved_per_successfully_verified_goal:
minutes saved are credited only when the goal is successfully verified.
Raw speed without verified completion is not success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loop_engineering.domain.models import (
    DELIVERABLE_VERDICTS,
    GoalMatchVerdict,
    RunState,
    Task,
    TaskStatus,
    VerificationResult,
)
from loop_engineering.runtime.duplicate_detection import ActionRegistry
from loop_engineering.verification.loop3_evidence import EvidenceCoverage
from loop_engineering.verification.loop4_stability import StabilityReport


@dataclass
class NorthStar:
    baseline_manual_minutes: float
    human_active_minutes: float
    goal_successfully_verified: bool
    estimated_minutes_saved: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": "human_active_minutes_saved_per_successfully_verified_goal",
            "baseline_manual_minutes": self.baseline_manual_minutes,
            "human_active_minutes": self.human_active_minutes,
            "goal_successfully_verified": self.goal_successfully_verified,
            "estimated_minutes_saved": self.estimated_minutes_saved,
        }


def north_star(
    contract: dict[str, Any], state: RunState, final_verdict: GoalMatchVerdict
) -> NorthStar:
    baseline = float(contract["north_star_metric"]["baseline_manual_minutes"])
    verified = final_verdict in DELIVERABLE_VERDICTS
    saved = max(0.0, baseline - state.human_active_minutes) if verified else 0.0
    return NorthStar(
        baseline_manual_minutes=baseline,
        human_active_minutes=state.human_active_minutes,
        goal_successfully_verified=verified,
        estimated_minutes_saved=round(saved, 1),
    )


def leading_metrics(
    tasks: list[Task],
    verifications: list[VerificationResult],
    state: RunState,
    actions: ActionRegistry | None = None,
    evidence: EvidenceCoverage | None = None,
    stability: StabilityReport | None = None,
    goal_match_score: int | None = None,
) -> dict[str, Any]:
    """The PD-03 leading metrics, computed from the run's own records."""
    planned = [t for t in tasks if t.repair_of is None]
    completed = [t for t in planned if t.status == TaskStatus.VERIFIED]

    loop1 = [v for v in verifications if v.loop == "loop1_task"]
    first_pass_by_task: dict[str, bool] = {}
    for v in sorted(loop1, key=lambda v: v.verified_at):
        first_pass_by_task.setdefault(v.subject_id, v.passed)
    first_pass_rate = (
        100.0 * sum(first_pass_by_task.values()) / len(first_pass_by_task)
        if first_pass_by_task
        else 0.0
    )

    repair_attempts = [max(0, t.attempts - 1) for t in tasks]
    avg_repair = sum(repair_attempts) / len(repair_attempts) if repair_attempts else 0.0

    repeated_rate = 0.0
    if actions is not None:
        counts = [len(v) for v in actions.to_dict().values()]
        total = sum(counts)
        repeats = sum(c - 1 for c in counts if c > 1)
        repeated_rate = 100.0 * repeats / total if total else 0.0

    consistency: float | None = None
    if stability is not None:
        decided = len(stability.stable) + len(stability.unstable)
        consistency = 100.0 * len(stability.stable) / decided if decided else 100.0

    return {
        "planned_tasks_completed_autonomously_pct": round(
            100.0 * len(completed) / len(planned) if planned else 0.0, 1
        ),
        "first_pass_task_verification_rate_pct": round(first_pass_rate, 1),
        "material_claims_independently_verified_pct": (
            evidence.supported_pct if evidence is not None else None
        ),
        "avg_repair_attempts_per_task": round(avg_repair, 2),
        "repeated_action_rate_pct": round(repeated_rate, 1),
        "human_interventions": state.human_interventions,
        "six_run_conclusion_consistency_pct": (
            round(consistency, 1) if consistency is not None else None
        ),
        "end_to_end_goal_match_score": goal_match_score,
    }
