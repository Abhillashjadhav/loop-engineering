"""Shared test fixtures and paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from loop_engineering.contracts import goal_contract

REPO_ROOT = Path(__file__).resolve().parents[1]


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
