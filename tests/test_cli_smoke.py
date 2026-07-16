"""CLI smoke tests: init, plan, run, status, verify, report, audit-github, resume."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.conftest import GITHUB_FIXTURES, REPO_ROOT

from loop_engineering.cli import main

SUBJECTS = str(REPO_ROOT / "examples" / "subjects.synthetic.yaml")
GOAL = str(REPO_ROOT / "examples" / "goal.synthetic.yaml")


@pytest.fixture
def workdir(tmp_path: Path):  # type: ignore[no-untyped-def]
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old)


def common(*extra: str) -> list[str]:
    return [*extra, "--subjects", SUBJECTS, "--fixtures", str(GITHUB_FIXTURES)]


def test_init_plan_run_status_verify_report(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["init", GOAL]) == 0
    out = capsys.readouterr().out
    assert "digest:  sha256:" in out
    assert (workdir / "contracts" / "github-authority-audit-synthetic.locked.yaml").is_file()

    assert main(common("plan", "github-authority-audit-synthetic")) == 0
    out = capsys.readouterr().out
    assert "atomic tasks" in out and "builder-1-identity" in out

    assert main(common("run", "github-authority-audit-synthetic")) == 0
    out = capsys.readouterr().out
    assert "GOAL_MATCH" in out and "accuracy evidence pack" in out

    run_dirs = list((workdir / "runs" / "github-authority-audit-synthetic").iterdir())
    assert len(run_dirs) == 1
    run_id = run_dirs[0].name

    assert main(["status", run_id]) == 0
    out = capsys.readouterr().out
    assert '"status": "COMPLETE"' in out and "z-2-final-output: VERIFIED" in out

    assert main(["verify", run_id]) == 0
    out = capsys.readouterr().out
    assert "gate A (read-only): COMPLETE" in out

    assert main(["report", run_id]) == 0
    out = capsys.readouterr().out
    assert "# Accuracy Evidence" in out


def test_audit_github_one_shot(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(common("audit-github", "--goal-file", GOAL)) == 0
    out = capsys.readouterr().out
    assert "GOAL_MATCH" in out


def test_interrupt_then_resume_cli(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    exit_code = main(common("audit-github", "--goal-file", GOAL, "--interrupt-after", "2"))
    assert exit_code == 2
    assert "simulated crash" in capsys.readouterr().err
    run_dirs = list((workdir / "runs" / "github-authority-audit-synthetic").iterdir())
    assert len(run_dirs) == 1
    assert main(common("resume", run_dirs[0].name)) == 0
    out = capsys.readouterr().out
    assert "GOAL_MATCH" in out


def test_live_mode_fails_loudly_without_network_access(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    exit_code = main(["audit-github", "--goal-file", GOAL, "--subjects", SUBJECTS, "--live"])
    assert exit_code != 0
    err = capsys.readouterr().err
    assert "live GitHub access is not available" in err or "BLOCKED" in err


def test_unknown_run_id_is_clear_error(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["status", "run-nope"]) == 2
    assert "cannot resolve run" in capsys.readouterr().err
