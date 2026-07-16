"""Shared fixtures: locked contracts, fixture paths, and a minimal demo use
case that lets engine-level behaviors (repair below 70, planted verification
failures) be exercised deterministically."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.models import (
    Claim,
    ClaimImpact,
    EvidenceItem,
    PassCondition,
    StabilityVariant,
    Task,
)
from loop_engineering.reporting.evidence_pack import LearningReceipt
from loop_engineering.runtime.engine import ExecutionContext, TaskOutcome
from loop_engineering.verification.loop4_stability import RunFindings

REPO_ROOT = Path(__file__).resolve().parents[1]
GITHUB_FIXTURES = REPO_ROOT / "evals" / "fixtures" / "github"


def make_contract_draft(**overrides: Any) -> dict[str, Any]:
    draft: dict[str, Any] = {
        "goal_id": "demo-goal",
        "version": 1,
        "goal_statement": "produce the demo report end to end",
        "expected_output": {
            "deliverables": ["report with verdict", "summary json"],
        },
        "north_star_metric": {
            "name": "human_active_minutes_saved_per_successfully_verified_goal",
            "baseline_manual_minutes": 60,
        },
        "leading_metrics": ["first-pass task verification rate"],
        "scope": ["produce the demo report"],
        "exclusions": ["anything outside the demo"],
        "allowed_actions": ["write files under the run directory"],
        "forbidden_actions": ["destructive operations"],
        "data_sources": ["local synthetic data"],
        "evidence_requirements": {
            "normal_claim_min_sources": 2,
            "high_impact_claim_min_sources": 3,
        },
        "success_checks": ["report exists and is verified"],
        "goal_match_threshold": 70,
        "replication_count": 1,
        "budget": {"max_iterations": 30, "max_task_attempts": 3},
        "stop_conditions": ["budget exhausted"],
        "escalation_conditions": ["human decision required"],
        "approved_at": "2026-07-16T00:00:00+00:00",
        "approved_by": "tests",
    }
    draft.update(overrides)
    return draft


@pytest.fixture
def locked_contract() -> dict[str, Any]:
    return goal_contract.lock(make_contract_draft())


def _demo_claim() -> Claim:
    return Claim(
        claim_id="demo-claim",
        text="the demo dataset contains one record",
        impact=ClaimImpact.NORMAL,
        evidence=[
            EvidenceItem(
                evidence_id="e1",
                source_url="local://data/source-a",
                origin="source_code",
                retrieved_at="2026-07-16T00:00:00+00:00",
                content_hash="sha256:aa",
            ),
            EvidenceItem(
                evidence_id="e2",
                source_url="local://data/source-b",
                origin="commit_history",
                retrieved_at="2026-07-16T00:00:00+00:00",
                content_hash="sha256:bb",
            ),
        ],
    )


class DemoUseCase:
    """Two-phase demo: the first pass deliberately under-delivers (no verdict,
    no summary.json) so Gate B lands below 70 and automatic repair kicks in.

    fail_first_attempt plants a Loop-1 verification failure on the first
    execution attempt (artifact missing the pass-condition text)."""

    name = "demo"

    def __init__(self, fail_first_attempt: bool = False) -> None:
        self.fail_first_attempt = fail_first_attempt

    def build_plan(self, contract: dict[str, Any], config: dict[str, Any]) -> list[Task]:
        return [
            Task(
                task_id="t1-report",
                goal_requirement="produce the demo report",
                action="write the demo report draft",
                expected_artifact="report.md",
                evidence_required=["source-a.txt"],
                pass_condition=PassCondition(type="file_contains", text="# Demo report"),
                failure_condition="report draft missing",
                max_attempts=3,
            )
        ]

    def stage_of(self, task: Task) -> str:
        return "demo"

    def execute_task(self, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        ctx.evidence_path("source-a.txt").write_text("raw demo source", encoding="utf-8")
        if task.task_id == "t1-report":
            if self.fail_first_attempt and task.attempts <= 1:
                ctx.artifact_path("report.md").write_text("broken draft", encoding="utf-8")
            else:
                ctx.artifact_path("report.md").write_text(
                    "# Demo report\n\ndraft without verdict\n", encoding="utf-8"
                )
            return TaskOutcome(claims=[_demo_claim()])
        if task.task_id.startswith("repair-"):
            ctx.artifact_path("report.md").write_text(
                "# Demo report\n\n## Verdict\n\nall good\n\nknown uncertainty: none material\n",
                encoding="utf-8",
            )
            ctx.artifact_path("summary.json").write_text(
                json.dumps({"status": "ok"}), encoding="utf-8"
            )
            return TaskOutcome()
        raise AssertionError(f"unexpected task {task.task_id}")

    def build_final_output(self, ctx: ExecutionContext) -> str:
        report = ctx.run_directory / "artifacts" / "report.md"
        return report.read_text(encoding="utf-8") if report.exists() else ""

    def run_variant(self, variant: StabilityVariant, ctx: ExecutionContext) -> RunFindings:
        return RunFindings(variant=variant, findings={"demo": "ok"})

    def deliverables_present(self, ctx: ExecutionContext) -> list[str]:
        present = []
        report = ctx.run_directory / "artifacts" / "report.md"
        if report.exists() and "## Verdict" in report.read_text(encoding="utf-8"):
            present.append("report with verdict")
        if (ctx.run_directory / "artifacts" / "summary.json").exists():
            present.append("summary json")
        return present

    def repair_tasks(
        self, weak_dimensions: list[str], ctx: ExecutionContext, existing: list[Task]
    ) -> list[Task]:
        n = sum(1 for t in existing if t.task_id.startswith("repair-"))
        return [
            Task(
                task_id=f"repair-{n + 1:03d}",
                goal_requirement="produce the demo report",
                action="repair the demo report to satisfy the output contract",
                expected_artifact="summary.json",
                evidence_required=[],
                pass_condition=PassCondition(type="json_valid"),
                failure_condition="summary still missing",
                repair_of="t1-report",
            )
        ]

    def scorecards(self, ctx: ExecutionContext) -> dict[str, dict[str, Any]]:
        return {}

    def learning_receipt(self, ctx: ExecutionContext) -> LearningReceipt:
        return LearningReceipt(important_decisions=["demo decision"])

    def limitations(self, ctx: ExecutionContext) -> list[str]:
        return ["demo limitation"]


class NeverPassesUseCase(DemoUseCase):
    """Planted failure: the artifact never satisfies the pass condition."""

    def execute_task(self, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        ctx.evidence_path("source-a.txt").write_text("raw demo source", encoding="utf-8")
        ctx.artifact_path("report.md").write_text("broken draft forever", encoding="utf-8")
        return TaskOutcome()


@pytest.fixture
def audit_subjects() -> list[dict[str, Any]]:
    import yaml

    with (REPO_ROOT / "examples" / "subjects.synthetic.yaml").open(encoding="utf-8") as fh:
        return [dict(s) for s in yaml.safe_load(fh)["subjects"]]


@pytest.fixture
def audit_contract() -> dict[str, Any]:
    draft = goal_contract.load_unlocked(REPO_ROOT / "examples" / "goal.synthetic.yaml")
    return goal_contract.lock(draft)
