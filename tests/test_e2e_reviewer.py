"""Gate A process completeness and Gate B PD-06 thresholds."""

from __future__ import annotations

from pathlib import Path

from loop_engineering.domain.models import (
    CheckResult,
    GateAVerdict,
    GoalMatchVerdict,
    PassCondition,
    RunState,
    RunStatus,
    Task,
    TaskStatus,
    VerificationResult,
    utc_now,
)
from loop_engineering.verification.e2e_reviewer import (
    GateAResult,
    GateBInputs,
    repair_targets,
    review_process,
    score_goal_match,
)
from loop_engineering.verification.loop3_evidence import EvidenceCoverage


def make_state(status: RunStatus = RunStatus.RUNNING) -> RunState:
    return RunState(
        goal_id="g",
        run_id="r",
        contract_digest="sha256:00",
        status=status,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def verified_task(task_id: str) -> Task:
    return Task(
        task_id=task_id,
        goal_requirement="req",
        action="act",
        expected_artifact="a.json",
        evidence_required=[],
        pass_condition=PassCondition(type="file_exists"),
        failure_condition="fc",
        status=TaskStatus.VERIFIED,
        artifact_digest="sha256:aa",
    )


def loop_result(loop: str, subject: str, passed: bool = True) -> VerificationResult:
    return VerificationResult(
        verification_id=f"{loop}-{subject}",
        loop=loop,
        subject_id=subject,
        verifier_role="verifier",
        passed=passed,
        checks=[],
        verified_at=utc_now(),
    )


def full_verifications(task_ids: list[str]) -> list[VerificationResult]:
    results = [loop_result("loop1_task", t) for t in task_ids]
    results.append(loop_result("loop2_drift", "all"))
    results.append(loop_result("loop3_evidence", "claims"))
    return results


def run_dir_with_evidence(tmp_path: Path) -> Path:
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence" / "raw.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_gate_a_complete(tmp_path: Path) -> None:
    tasks = [verified_task("a")]
    result = review_process(
        make_state(RunStatus.COMPLETE),
        tasks,
        full_verifications(["a"]),
        run_dir_with_evidence(tmp_path),
        stability_required=False,
    )
    assert result.verdict == GateAVerdict.COMPLETE


def test_gate_a_incomplete_on_pending_task(tmp_path: Path) -> None:
    tasks = [verified_task("a")]
    pending = verified_task("b")
    pending.status = TaskStatus.EXECUTED
    result = review_process(
        make_state(),
        [*tasks, pending],
        full_verifications(["a"]),
        run_dir_with_evidence(tmp_path),
        stability_required=False,
    )
    assert result.verdict == GateAVerdict.INCOMPLETE


def test_gate_a_interrupted(tmp_path: Path) -> None:
    result = review_process(
        make_state(RunStatus.INTERRUPTED),
        [verified_task("a")],
        full_verifications(["a"]),
        run_dir_with_evidence(tmp_path),
        stability_required=False,
    )
    assert result.verdict == GateAVerdict.INTERRUPTED


def test_gate_a_evidence_missing(tmp_path: Path) -> None:
    result = review_process(
        make_state(RunStatus.COMPLETE),
        [verified_task("a")],
        full_verifications(["a"]),
        tmp_path,  # no evidence files at all
        stability_required=False,
    )
    assert result.verdict == GateAVerdict.EVIDENCE_MISSING


def test_gate_a_requires_loop4_when_stability_required(tmp_path: Path) -> None:
    result = review_process(
        make_state(RunStatus.COMPLETE),
        [verified_task("a")],
        full_verifications(["a"]),
        run_dir_with_evidence(tmp_path),
        stability_required=True,
    )
    assert result.verdict == GateAVerdict.INCOMPLETE


def test_gate_a_verified_status_needs_loop1_record(tmp_path: Path) -> None:
    result = review_process(
        make_state(RunStatus.COMPLETE),
        [verified_task("a")],
        [loop_result("loop2_drift", "all"), loop_result("loop3_evidence", "claims")],
        run_dir_with_evidence(tmp_path),
        stability_required=False,
    )
    assert result.verdict == GateAVerdict.INCOMPLETE


def gate_a_complete() -> GateAResult:
    return GateAResult(verdict=GateAVerdict.COMPLETE, checks=[CheckResult("ok", True)])


def inputs(score_profile: str) -> GateBInputs:
    cov = EvidenceCoverage(
        total_claims=4, supported_claims=4, unsupported_claim_ids=[], conflicted_claim_ids=[]
    )
    if score_profile == "full":
        return GateBInputs(6, 6, ["a"], ["a"], True, 0, cov, True, True)
    if score_profile == "caveat":  # deliverables half-present, weak disclosure -> 70s
        return GateBInputs(6, 6, ["a", "b"], ["a"], True, 0, cov, False, False)
    return GateBInputs(6, 4, ["a", "b"], [], True, 1, cov, False, False)  # low


def test_gate_b_80_plus_is_goal_match() -> None:
    result = score_goal_match(inputs("full"), gate_a_complete())
    assert result.score >= 80 and result.verdict == GoalMatchVerdict.GOAL_MATCH
    assert not result.repair_needed


def test_gate_b_70s_delivers_with_caveats() -> None:
    result = score_goal_match(inputs("caveat"), gate_a_complete())
    assert 70 <= result.score < 80
    assert result.verdict == GoalMatchVerdict.GOAL_MATCH_WITH_CAVEATS
    assert result.caveats and not result.repair_needed


def test_gate_b_below_70_requires_repair() -> None:
    result = score_goal_match(inputs("low"), gate_a_complete())
    assert result.score < 70 and result.verdict == GoalMatchVerdict.PARTIAL_MATCH
    assert result.repair_needed
    targets = repair_targets(inputs("low"), result)
    assert targets and targets[0] in result.dimension_scores


def test_no_success_on_interrupted_or_incomplete() -> None:
    interrupted = GateAResult(GateAVerdict.INTERRUPTED, [])
    result = score_goal_match(inputs("full"), interrupted)
    assert result.verdict == GoalMatchVerdict.INTERRUPTED and result.score == 0
    incomplete = GateAResult(GateAVerdict.INCOMPLETE, [])
    result = score_goal_match(inputs("full"), incomplete)
    assert result.verdict == GoalMatchVerdict.INCOMPLETE
    missing = GateAResult(GateAVerdict.EVIDENCE_MISSING, [])
    result = score_goal_match(inputs("full"), missing)
    assert result.verdict == GoalMatchVerdict.NOT_PROVEN
