"""CLI refusals happen before a run or resume is mutated."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from tests.conftest import GITHUB_FIXTURES, REPO_ROOT

from loop_engineering.cli import main

GOAL = REPO_ROOT / "examples" / "goal.synthetic.yaml"
SUBJECTS = REPO_ROOT / "examples" / "subjects.synthetic.yaml"


@pytest.fixture
def workdir(tmp_path: Path):  # type: ignore[no-untyped-def]
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(previous)


def _audit(*extra: str) -> list[str]:
    return [
        "audit-github",
        "--goal-file",
        str(GOAL),
        "--subjects",
        str(SUBJECTS),
        "--fixtures",
        str(GITHUB_FIXTURES),
        *extra,
    ]


def _interrupted_run(workdir: Path, capsys) -> Path:  # type: ignore[no-untyped-def]
    assert main(_audit("--interrupt-after", "2")) == 2
    capsys.readouterr()
    return next((workdir / "runs" / "github-authority-audit-synthetic").iterdir())


def _saved_bytes(run_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(run_dir)): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "suffix,content",
    [
        (".yaml", b"goal_id: [unterminated"),
        (".json", b'{"goal_id": '),
        (".yaml", b"goal_id: \xff"),
    ],
)
def test_malformed_goal_is_controlled_before_writing(
    workdir: Path, capsys, suffix: str, content: bytes
) -> None:  # type: ignore[no-untyped-def]
    bad = workdir / f"bad-goal{suffix}"
    bad.write_bytes(content)
    for command in (
        ["init", str(bad)],
        [
            "audit-github",
            "--goal-file",
            str(bad),
            "--subjects",
            str(SUBJECTS),
            "--fixtures",
            str(GITHUB_FIXTURES),
        ],
    ):
        assert main(command) == 2
        err = capsys.readouterr().err
        assert "error:" in err and str(bad) in err and "Traceback" not in err
    assert not (workdir / "runs").exists()
    assert not (workdir / "contracts").exists()


@pytest.mark.parametrize("variant", ["yaml_date", "yaml_cycle"])
def test_yaml_values_outside_json_domain_are_controlled_before_writing(
    workdir: Path, capsys, variant: str
) -> None:  # type: ignore[no-untyped-def]
    source = GOAL.read_text(encoding="utf-8")
    if variant == "yaml_date":
        content = source.replace(
            'approved_at: "2026-07-16T00:00:00+00:00"', "approved_at: 2026-07-16"
        )
    else:
        content = source + "\ncycle: &cycle [*cycle]\n"
    goal = workdir / "non-json-domain.yaml"
    goal.write_text(content, encoding="utf-8")
    for command in (
        ["init", str(goal)],
        [
            "audit-github",
            "--goal-file",
            str(goal),
            "--subjects",
            str(SUBJECTS),
            "--fixtures",
            str(GITHUB_FIXTURES),
        ],
    ):
        assert main(command) == 2
        err = capsys.readouterr().err
        assert "error:" in err and str(goal) in err and "Traceback" not in err
    assert not (workdir / "runs").exists()
    assert not (workdir / "contracts").exists()


@pytest.mark.parametrize(
    "content",
    [
        "subjects: [unterminated",
        "subjects: wrong-shape\n",
        "subjects:\n  - string-item\n",
        "subjects:\n  - display_name: Missing slug\n    candidate_login: fixture\n",
    ],
)
def test_bad_subjects_fail_before_new_run(workdir: Path, capsys, content: str) -> None:  # type: ignore[no-untyped-def]
    bad = workdir / "bad-subjects.yaml"
    bad.write_text(content, encoding="utf-8")
    assert main(["init", str(GOAL)]) == 0
    capsys.readouterr()
    for command in ("plan", "run"):
        assert (
            main(
                [
                    command,
                    "github-authority-audit-synthetic",
                    "--subjects",
                    str(bad),
                    "--fixtures",
                    str(GITHUB_FIXTURES),
                ]
            )
            == 2
        )
        err = capsys.readouterr().err
        assert "error:" in err and "subjects" in err and "Traceback" not in err
    assert not (workdir / "runs").exists()


def test_subjects_invalid_utf8_is_controlled(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    bad = workdir / "bad-subjects.yaml"
    bad.write_bytes(b"subjects: \xff")
    assert main(["init", str(GOAL)]) == 0
    capsys.readouterr()
    assert main(["plan", "github-authority-audit-synthetic", "--subjects", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "UTF-8" in err and "Traceback" not in err


def test_plan_can_use_explicit_subjects_without_a_snapshot(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["init", str(GOAL)]) == 0
    capsys.readouterr()
    assert main(["plan", "github-authority-audit-synthetic", "--subjects", str(SUBJECTS)]) == 0
    assert "atomic tasks" in capsys.readouterr().out
    assert not (workdir / "runs").exists()


def test_custom_absolute_inputs_resume_without_repeating_verified_tasks(
    workdir: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    custom_subjects = workdir / "custom-subjects.yaml"
    custom_subjects.write_bytes(SUBJECTS.read_bytes())
    custom_fixtures = workdir / "custom-fixtures"
    shutil.copytree(GITHUB_FIXTURES, custom_fixtures)
    command = [
        "audit-github",
        "--goal-file",
        str(GOAL),
        "--subjects",
        str(custom_subjects),
        "--fixtures",
        str(custom_fixtures),
        "--interrupt-after",
        "3",
    ]
    assert main(command) == 2
    capsys.readouterr()
    run_dir = next((workdir / "runs" / "github-authority-audit-synthetic").iterdir())
    ledger = run_dir / "task-ledger.jsonl"
    prior_rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    verified = {row["task_id"] for row in prior_rows if row["to"] == "VERIFIED"}
    assert verified
    assert (
        main(
            [
                "resume",
                str(run_dir),
                "--subjects",
                str(custom_subjects),
                "--fixtures",
                str(custom_fixtures),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["verify", str(run_dir)]) == 0
    assert "COMPLETE" in capsys.readouterr().out
    final_rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    for task_id in verified:
        assert sum(row["task_id"] == task_id and row["to"] == "VERIFIED" for row in final_rows) == 1


def test_resume_requires_explicit_source_without_mutating_run(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    run_dir = _interrupted_run(workdir, capsys)
    before = _saved_bytes(run_dir)
    assert main(["resume", str(run_dir)]) == 2
    assert "--subjects" in capsys.readouterr().err
    assert _saved_bytes(run_dir) == before


def test_resume_bad_source_is_refused_before_mutation(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    run_dir = _interrupted_run(workdir, capsys)
    before = _saved_bytes(run_dir)
    missing = workdir / "absent-fixtures"
    assert (
        main(["resume", str(run_dir), "--subjects", str(SUBJECTS), "--fixtures", str(missing)]) == 2
    )
    assert "fixture" in capsys.readouterr().err
    assert _saved_bytes(run_dir) == before

    corrupt = workdir / "corrupt-fixtures"
    shutil.copytree(GITHUB_FIXTURES, corrupt)
    (corrupt / "profiles" / "synthetic-builder.json").write_text("{", encoding="utf-8")
    assert (
        main(["resume", str(run_dir), "--subjects", str(SUBJECTS), "--fixtures", str(corrupt)]) == 2
    )
    assert "fixture" in capsys.readouterr().err
    assert _saved_bytes(run_dir) == before


def test_corrupt_run_contract_is_controlled_and_read_only(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    run_dir = _interrupted_run(workdir, capsys)
    (run_dir / "contract.yaml").write_text("goal_id: [unterminated", encoding="utf-8")
    before = _saved_bytes(run_dir)
    for command in (
        ["resume", str(run_dir), "--subjects", str(SUBJECTS), "--fixtures", str(GITHUB_FIXTURES)],
        ["verify", str(run_dir)],
    ):
        assert main(command) == 2
        err = capsys.readouterr().err
        assert "error:" in err and "contract" in err and "Traceback" not in err
        assert _saved_bytes(run_dir) == before


@pytest.mark.parametrize("variant", ["yaml_date", "yaml_cycle"])
def test_non_json_run_contract_is_controlled_and_read_only(
    workdir: Path, capsys, variant: str
) -> None:  # type: ignore[no-untyped-def]
    run_dir = _interrupted_run(workdir, capsys)
    contract_path = run_dir / "contract.yaml"
    source = contract_path.read_text(encoding="utf-8")
    if variant == "yaml_date":
        content = source.replace(
            "approved_at: '2026-07-16T00:00:00+00:00'", "approved_at: 2026-07-16"
        )
        assert content != source
    else:
        content = source + "\ncycle: &cycle [*cycle]\n"
    contract_path.write_text(content, encoding="utf-8")
    before = _saved_bytes(run_dir)
    for command in (
        [
            "resume",
            str(run_dir),
            "--subjects",
            str(SUBJECTS),
            "--fixtures",
            str(GITHUB_FIXTURES),
        ],
        ["verify", str(run_dir)],
    ):
        assert main(command) == 2
        err = capsys.readouterr().err
        assert "error:" in err and "contract" in err and "Traceback" not in err
        assert _saved_bytes(run_dir) == before


def test_mode_conflict_or_unavailable_live_refused_before_run(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    for command in (
        _audit("--live"),
        ["audit-github", "--goal-file", str(GOAL), "--subjects", str(SUBJECTS), "--live"],
    ):
        assert main(command) == 2
        err = capsys.readouterr().err
        assert "error:" in err and "Traceback" not in err
    assert not (workdir / "runs").exists()
    assert not (workdir / "contracts").exists()


def test_bad_source_refused_before_lock_or_run(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    corrupt = workdir / "corrupt-fixtures"
    shutil.copytree(GITHUB_FIXTURES, corrupt)
    (corrupt / "profiles" / "synthetic-builder.json").write_text("{", encoding="utf-8")
    assert (
        main(
            [
                "audit-github",
                "--goal-file",
                str(GOAL),
                "--subjects",
                str(SUBJECTS),
                "--fixtures",
                str(corrupt),
            ]
        )
        == 2
    )
    assert "fixture source" in capsys.readouterr().err
    assert not (workdir / "runs").exists()
    assert not (workdir / "contracts").exists()


def test_resume_live_and_conflicting_modes_preserve_saved_run(workdir: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    run_dir = _interrupted_run(workdir, capsys)
    before = _saved_bytes(run_dir)
    for options in (
        ["--subjects", str(SUBJECTS), "--live"],
        ["--subjects", str(SUBJECTS), "--fixtures", str(GITHUB_FIXTURES), "--live"],
    ):
        assert main(["resume", str(run_dir), *options]) == 2
        assert "error:" in capsys.readouterr().err
        assert _saved_bytes(run_dir) == before
