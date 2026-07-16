"""Loop 1: filesystem-only verification and the self-verification prohibition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_engineering.domain.errors import SelfVerificationError
from loop_engineering.domain.models import PassCondition, Task
from loop_engineering.verification.loop1_task import verify_task


def make_task(pass_condition: PassCondition, evidence: list[str] | None = None) -> Task:
    return Task(
        task_id="t1",
        goal_requirement="req",
        action="act",
        expected_artifact="out.json",
        evidence_required=evidence or [],
        pass_condition=pass_condition,
        failure_condition="fc",
    )


def prep_run(tmp_path: Path, artifact_content: str | None = '{"items": [1, 2]}') -> Path:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "evidence").mkdir()
    if artifact_content is not None:
        (tmp_path / "artifacts" / "out.json").write_text(artifact_content, encoding="utf-8")
    return tmp_path


def test_passes_with_artifact_evidence_and_condition(tmp_path: Path) -> None:
    run = prep_run(tmp_path)
    (run / "evidence" / "raw.txt").write_text("raw", encoding="utf-8")
    task = make_task(PassCondition(type="json_has_keys", keys=["items"]), ["raw.txt"])
    result = verify_task(task, run)
    assert result.passed
    assert task.artifact_digest and task.artifact_digest.startswith("sha256:")
    assert result.executor_role != result.verifier_role


def test_missing_artifact_fails(tmp_path: Path) -> None:
    run = prep_run(tmp_path, artifact_content=None)
    result = verify_task(make_task(PassCondition(type="file_exists")), run)
    assert not result.passed
    assert "artifact_exists" in (result.failure_reason or "")


def test_missing_evidence_fails_even_with_artifact(tmp_path: Path) -> None:
    run = prep_run(tmp_path)
    task = make_task(PassCondition(type="file_exists"), ["never-written.txt"])
    result = verify_task(task, run)
    assert not result.passed
    assert "evidence_present" in (result.failure_reason or "")


def test_min_count_condition(tmp_path: Path) -> None:
    run = prep_run(tmp_path, json.dumps({"records": [1]}))
    ok = verify_task(make_task(PassCondition(type="min_count", count_key="records", min=1)), run)
    assert ok.passed
    bad = verify_task(make_task(PassCondition(type="min_count", count_key="records", min=5)), run)
    assert not bad.passed


def test_executor_statement_is_not_an_input(tmp_path: Path) -> None:
    # verify_task's signature admits only the task and the filesystem — there is
    # no channel for an executor narrative. The artifact alone decides.
    run = prep_run(tmp_path, "not json at all")
    result = verify_task(make_task(PassCondition(type="json_valid")), run)
    assert not result.passed


def test_self_verification_forbidden(tmp_path: Path) -> None:
    run = prep_run(tmp_path)
    with pytest.raises(SelfVerificationError):
        verify_task(
            make_task(PassCondition(type="file_exists")),
            run,
            executor_role="executor",
            verifier_role="executor",
        )
