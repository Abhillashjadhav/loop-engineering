"""North Star crediting rules, leading metrics, and the Accuracy Evidence Pack."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import DemoUseCase, make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.models import GoalMatchVerdict, RunState, RunStatus, utc_now
from loop_engineering.reporting.metrics import north_star
from loop_engineering.runtime.engine import Engine


def make_state(minutes: float = 5.0) -> RunState:
    return RunState(
        goal_id="g",
        run_id="r",
        contract_digest="sha256:00",
        status=RunStatus.COMPLETE,
        created_at=utc_now(),
        updated_at=utc_now(),
        human_active_minutes=minutes,
    )


def test_north_star_credits_only_verified_goals() -> None:
    contract = goal_contract.lock(make_contract_draft())
    ns = north_star(contract, make_state(), GoalMatchVerdict.GOAL_MATCH)
    assert ns.goal_successfully_verified and ns.estimated_minutes_saved == 55.0
    ns = north_star(contract, make_state(), GoalMatchVerdict.GOAL_MATCH_WITH_CAVEATS)
    assert ns.goal_successfully_verified
    for verdict in (
        GoalMatchVerdict.PARTIAL_MATCH,
        GoalMatchVerdict.GOAL_MISMATCH,
        GoalMatchVerdict.NOT_PROVEN,
        GoalMatchVerdict.INCOMPLETE,
        GoalMatchVerdict.INTERRUPTED,
    ):
        ns = north_star(contract, make_state(), verdict)
        assert not ns.goal_successfully_verified
        assert ns.estimated_minutes_saved == 0.0  # raw speed without verification is not success


def test_pack_generated_by_full_run(tmp_path: Path, audit_contract, audit_subjects) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import GITHUB_FIXTURES

    from loop_engineering.runtime.engine import Engine
    from loop_engineering.use_cases.github_authority_audit.datasource import FixtureDataSource
    from loop_engineering.use_cases.github_authority_audit.runner import AuditUseCase

    use_case = AuditUseCase(FixtureDataSource(GITHUB_FIXTURES), audit_subjects)
    engine = Engine(
        audit_contract,
        use_case,
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    result = engine.run()
    assert result.pack_dir is not None
    expected_files = [
        "final-output.md",
        "accuracy-evidence.md",
        "accuracy-evidence.json",
        "learning-receipt.md",
        "claim-evidence-matrix.csv",
        "task-ledger.jsonl",
        "verification-results.jsonl",
        "six-run-comparison.md",
        "end-to-end-goal-review.md",
        "unresolved-uncertainties.md",
    ]
    for name in expected_files:
        assert (result.pack_dir / name).is_file(), name
    assert any((result.pack_dir / "repository-scorecards").glob("*.json"))
    accuracy = (result.pack_dir / "accuracy-evidence.md").read_text(encoding="utf-8")
    for heading in (
        "Process completeness",
        "Claim evidence coverage",
        "Six-run agreement",
        "Goal drift",
        "End-to-end goal-match score",
        "Exclusions and limitations",
    ):
        assert heading in accuracy, heading
    receipt = (result.pack_dir / "learning-receipt.md").read_text(encoding="utf-8")
    assert "Important decisions" in receipt and "Alternatives rejected" in receipt


def test_pack_generated_by_demo_run(tmp_path: Path) -> None:
    contract = goal_contract.lock(make_contract_draft())
    engine = Engine(
        contract,
        DemoUseCase(),
        runs_root=tmp_path / "runs",
        config={"outputs_root": str(tmp_path / "outputs")},
    )
    result = engine.run()
    assert result.pack_dir is not None
    expected_files = [
        "final-output.md",
        "accuracy-evidence.md",
        "accuracy-evidence.json",
        "learning-receipt.md",
        "claim-evidence-matrix.csv",
        "task-ledger.jsonl",
        "verification-results.jsonl",
        "end-to-end-goal-review.md",
        "unresolved-uncertainties.md",
    ]
    for name in expected_files:
        assert (result.pack_dir / name).is_file(), name
    accuracy = (result.pack_dir / "accuracy-evidence.md").read_text(encoding="utf-8")
    for heading in (
        "Process completeness",
        "Claim evidence coverage",
        "Goal drift",
        "End-to-end goal-match score",
        "North Star outcome",
        "Exclusions and limitations",
    ):
        assert heading in accuracy, heading
    receipt = (result.pack_dir / "learning-receipt.md").read_text(encoding="utf-8")
    assert "Important decisions" in receipt and "Alternatives rejected" in receipt
    # replication_count=1 -> six-run comparison rightly absent for the demo goal
    assert not (result.pack_dir / "six-run-comparison.md").exists()
