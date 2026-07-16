"""End-to-End Goal Reviewer (spec §7) — fresh-context, read-only.

Gate A proves process completeness; Gate B scores goal/output match 0-100 and
applies the PD-06 thresholds. Below 70 the runtime must create repair tasks
and continue; only GOAL_MATCH and GOAL_MATCH_WITH_CAVEATS may be delivered as
success.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loop_engineering.domain.models import (
    CheckResult,
    GateAVerdict,
    GoalMatchVerdict,
    RunState,
    RunStatus,
    Task,
    TaskStatus,
    VerificationResult,
    utc_now,
)
from loop_engineering.verification.loop3_evidence import EvidenceCoverage

REVIEWER_ROLE = "end-to-end-goal-reviewer"

GOAL_MATCH_FLOOR = 80
CAVEAT_FLOOR = 70


@dataclass
class GateAResult:
    verdict: GateAVerdict
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict.value, "checks": [c.to_dict() for c in self.checks]}


@dataclass
class GateBInputs:
    """Structured, independently measurable inputs to the goal-match score."""

    requirements_total: int
    requirements_covered: int
    deliverables_expected: list[str]
    deliverables_present: list[str]
    north_star_captured: bool
    scope_violations: int
    evidence_coverage: EvidenceCoverage | None
    uncertainty_disclosed: bool
    actionable_conclusion: bool


@dataclass
class GateBResult:
    score: int
    verdict: GoalMatchVerdict
    dimension_scores: dict[str, float]
    repair_needed: bool
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "verdict": self.verdict.value,
            "dimension_scores": dict(self.dimension_scores),
            "repair_needed": self.repair_needed,
            "caveats": list(self.caveats),
        }


def review_process(
    state: RunState,
    tasks: list[Task],
    verifications: list[VerificationResult],
    run_directory: str | Path,
    stability_required: bool,
) -> GateAResult:
    """Gate A — process completeness (spec §7)."""
    run_dir = Path(run_directory)
    checks: list[CheckResult] = []

    pending = [
        t.task_id
        for t in tasks
        if t.status not in (TaskStatus.VERIFIED, TaskStatus.SKIPPED_WITH_REASON)
    ]
    checks.append(
        CheckResult(
            "every_required_task_verified",
            not pending,
            f"non-terminal tasks: {pending}" if pending else f"{len(tasks)} task(s) terminal",
        )
    )

    verified_subjects = {v.subject_id for v in verifications if v.loop == "loop1_task" and v.passed}
    unverified = [
        t.task_id
        for t in tasks
        if t.status == TaskStatus.VERIFIED and t.task_id not in verified_subjects
    ]
    checks.append(
        CheckResult(
            "verified_status_backed_by_loop1_result",
            not unverified,
            f"VERIFIED without a passing loop1 record: {unverified}" if unverified else "",
        )
    )

    repaired = [t for t in tasks if t.repair_of is not None]
    reverified = [t.task_id for t in repaired if t.status == TaskStatus.VERIFIED]
    checks.append(
        CheckResult(
            "repairs_reverified",
            len(reverified) == len(repaired),
            f"{len(reverified)}/{len(repaired)} repair task(s) reverified",
        )
    )

    loops_present = {v.loop for v in verifications}
    required_loops = {"loop1_task", "loop2_drift", "loop3_evidence"}
    if stability_required:
        required_loops.add("loop4_stability")
    missing_loops = sorted(required_loops - loops_present)
    checks.append(
        CheckResult(
            "all_required_loops_ran",
            not missing_loops,
            f"missing loops: {missing_loops}" if missing_loops else "",
        )
    )

    interrupted = state.status in (RunStatus.INTERRUPTED, RunStatus.BLOCKED)
    checks.append(
        CheckResult(
            "run_not_interrupted",
            not interrupted,
            f"run status: {state.status.value}",
        )
    )

    evidence_dir = run_dir / "evidence"
    evidence_files = list(evidence_dir.rglob("*")) if evidence_dir.exists() else []
    digests_missing = [
        t.task_id for t in tasks if t.status == TaskStatus.VERIFIED and not t.artifact_digest
    ]
    checks.append(
        CheckResult(
            "evidence_files_and_digests_exist",
            bool(evidence_files) and not digests_missing,
            f"evidence files: {len(evidence_files)}, verified tasks missing digest: "
            f"{digests_missing}",
        )
    )

    failed_names = {c.name for c in checks if not c.passed}
    if not failed_names:
        verdict = GateAVerdict.COMPLETE
    elif "run_not_interrupted" in failed_names:
        verdict = GateAVerdict.INTERRUPTED
    elif "evidence_files_and_digests_exist" in failed_names and len(failed_names) == 1:
        verdict = GateAVerdict.EVIDENCE_MISSING
    else:
        verdict = GateAVerdict.INCOMPLETE
    return GateAResult(verdict=verdict, checks=checks)


_DIMENSION_WEIGHTS: dict[str, float] = {
    "goal_coverage": 0.25,
    "output_contract": 0.20,
    "north_star_outcome": 0.10,
    "scope_discipline": 0.10,
    "evidence_quality": 0.20,
    "uncertainty_disclosure": 0.10,
    "actionable_conclusion": 0.05,
}


def score_goal_match(inputs: GateBInputs, gate_a: GateAResult) -> GateBResult:
    """Gate B — goal/output match, 0-100, PD-06 thresholds.

    An interrupted or incomplete process can never score as success: Gate A
    verdicts other than COMPLETE map directly to non-deliverable verdicts.
    """
    if gate_a.verdict == GateAVerdict.INTERRUPTED:
        return GateBResult(0, GoalMatchVerdict.INTERRUPTED, {}, repair_needed=False)
    if gate_a.verdict == GateAVerdict.INCOMPLETE:
        return GateBResult(0, GoalMatchVerdict.INCOMPLETE, {}, repair_needed=True)
    if gate_a.verdict == GateAVerdict.EVIDENCE_MISSING:
        return GateBResult(0, GoalMatchVerdict.NOT_PROVEN, {}, repair_needed=True)

    dims: dict[str, float] = {}
    dims["goal_coverage"] = (
        100.0 * inputs.requirements_covered / inputs.requirements_total
        if inputs.requirements_total
        else 0.0
    )
    expected = set(inputs.deliverables_expected)
    present = expected.intersection(inputs.deliverables_present)
    dims["output_contract"] = 100.0 * len(present) / len(expected) if expected else 0.0
    dims["north_star_outcome"] = 100.0 if inputs.north_star_captured else 0.0
    dims["scope_discipline"] = max(0.0, 100.0 - 25.0 * inputs.scope_violations)
    if inputs.evidence_coverage is None or inputs.evidence_coverage.total_claims == 0:
        dims["evidence_quality"] = 0.0
    else:
        dims["evidence_quality"] = inputs.evidence_coverage.supported_pct
    dims["uncertainty_disclosure"] = 100.0 if inputs.uncertainty_disclosed else 0.0
    dims["actionable_conclusion"] = 100.0 if inputs.actionable_conclusion else 0.0

    score = round(sum(dims[k] * w for k, w in _DIMENSION_WEIGHTS.items()))
    score = max(0, min(100, score))

    caveats: list[str] = []
    if score >= GOAL_MATCH_FLOOR:
        verdict = GoalMatchVerdict.GOAL_MATCH
        repair = False
    elif score >= CAVEAT_FLOOR:
        verdict = GoalMatchVerdict.GOAL_MATCH_WITH_CAVEATS
        repair = False
        caveats = [f"{name}: {value:.0f}/100" for name, value in dims.items() if value < 100.0]
    else:
        verdict = GoalMatchVerdict.PARTIAL_MATCH
        repair = True
    return GateBResult(
        score=score,
        verdict=verdict,
        dimension_scores={k: round(v, 1) for k, v in dims.items()},
        repair_needed=repair,
        caveats=caveats,
    )


def repair_targets(inputs: GateBInputs, result: GateBResult) -> list[str]:
    """Which dimensions must improve, worst first — feeds automatic repair."""
    if not result.repair_needed:
        return []
    ranked = sorted(result.dimension_scores.items(), key=lambda kv: kv[1])
    return [name for name, value in ranked if value < 100.0]


def as_verification_result(gate_a: GateAResult, gate_b: GateBResult) -> VerificationResult:
    checks = list(gate_a.checks)
    checks.append(
        CheckResult(
            "goal_match_score",
            gate_b.verdict.value in ("GOAL_MATCH", "GOAL_MATCH_WITH_CAVEATS"),
            f"score={gate_b.score}, verdict={gate_b.verdict.value}",
        )
    )
    passed = all(c.passed for c in checks)
    return VerificationResult(
        verification_id=f"e2e-{uuid.uuid4().hex[:8]}",
        loop="e2e_review",
        subject_id="final_output",
        verifier_role=REVIEWER_ROLE,
        passed=passed,
        checks=checks,
        failure_reason=None
        if passed
        else f"gate_a={gate_a.verdict.value}, gate_b={gate_b.verdict.value}",
        verified_at=utc_now(),
    )
