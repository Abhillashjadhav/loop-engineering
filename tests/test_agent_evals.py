"""Agent eval fixtures: structure, permission policy, and prohibition coverage."""

from __future__ import annotations

from typing import Any

import yaml
from tests.conftest import REPO_ROOT

AGENTS = (
    "planner",
    "executor",
    "task-verifier",
    "goal-drift-reviewer",
    "evidence-verifier",
    "stability-reviewer",
    "end-to-end-goal-reviewer",
    "recovery-controller",
)

REQUIRED_KEYS = {
    "agent",
    "input_contract",
    "output_schema",
    "permissions",
    "prohibitions",
    "cases",
    "planted_failure",
    "goal_drift_handling",
    "uncertainty_handling",
    "self_verification",
}

READ_ONLY_AGENTS = {
    "planner",
    "task-verifier",
    "goal-drift-reviewer",
    "evidence-verifier",
    "stability-reviewer",
    "end-to-end-goal-reviewer",
}


def load_cases(agent: str) -> dict[str, Any]:
    path = REPO_ROOT / "evals" / "agents" / agent / "cases.yaml"
    assert path.is_file(), f"missing eval fixture for {agent}"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict)
    return data


def test_every_agent_has_eval_fixture_and_definition() -> None:
    for agent in AGENTS:
        data = load_cases(agent)
        missing = REQUIRED_KEYS - set(data)
        assert not missing, f"{agent}: missing keys {missing}"
        assert data["agent"] == agent
        agent_md = REPO_ROOT / ".claude" / "agents" / f"{agent}.md"
        assert agent_md.is_file(), f"missing agent definition {agent_md}"


def test_fire_and_no_fire_cases_present() -> None:
    for agent in AGENTS:
        cases = load_cases(agent)["cases"]
        assert cases.get("fire"), f"{agent}: no fire cases"
        assert cases.get("no_fire"), f"{agent}: no no-fire cases"
        for case in [*cases["fire"], *cases["no_fire"]]:
            assert {"name", "given", "expect"} <= set(case), f"{agent}: malformed case {case}"


def test_read_write_permission_policy() -> None:
    for agent in AGENTS:
        perms = load_cases(agent)["permissions"]
        if agent in READ_ONLY_AGENTS:
            assert perms["read_only"] is True, f"{agent} must be read-only"
        writable = set(perms.get("may_write", []))
        assert "state" not in writable and "ledger" not in writable, (
            f"{agent} may never write runtime state directly"
        )
        if agent == "executor":
            assert writable == {"artifacts", "evidence"}
            assert "verifications" not in writable


def test_executor_prohibited_from_self_verification() -> None:
    executor = load_cases("executor")
    assert any("verify" in p.lower() for p in executor["prohibitions"])
    assert "forbidden" in str(executor["self_verification"]).lower()


def test_planted_failures_are_detectable() -> None:
    for agent in AGENTS:
        planted = load_cases(agent)["planted_failure"]
        assert {"name", "given", "expect"} <= set(planted), agent
        assert planted["expect"], f"{agent}: planted failure needs an expected detection"


def test_skill_entry_point_exists() -> None:
    skill = REPO_ROOT / ".claude" / "skills" / "loop-engineer" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    for mode in ("start", "status", "resume", "report", "verify-only", "use-case"):
        assert mode in text, f"skill missing mode {mode}"
