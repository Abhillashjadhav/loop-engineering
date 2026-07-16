"""Schema validity for persisted records, plus a repo-wide secret scan."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
from tests.conftest import REPO_ROOT

from loop_engineering.domain.models import (
    PassCondition,
    RunState,
    RunStatus,
    Task,
    utc_now,
)
from loop_engineering.verification.loop1_task import verify_task

SCHEMAS = REPO_ROOT / "schemas"


def load_schema(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_all_schemas_are_valid_jsonschema() -> None:
    for path in SCHEMAS.glob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(load_schema(path.name))


def test_task_serialization_matches_schema() -> None:
    task = Task(
        task_id="t1",
        goal_requirement="req",
        action="act",
        expected_artifact="a.json",
        evidence_required=["e.txt"],
        pass_condition=PassCondition(type="json_has_keys", keys=["k"]),
        failure_condition="fc",
    )
    jsonschema.validate(task.to_dict(), load_schema("task.schema.json"))
    assert Task.from_dict(task.to_dict()).to_dict() == task.to_dict()


def test_run_state_matches_schema() -> None:
    state = RunState(
        goal_id="g",
        run_id="r",
        contract_digest="sha256:00",
        status=RunStatus.RUNNING,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    jsonschema.validate(state.to_dict(), load_schema("run-state.schema.json"))


def test_verification_result_matches_schema(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "artifacts" / "a.json").write_text("{}", encoding="utf-8")
    task = Task(
        task_id="t1",
        goal_requirement="req",
        action="act",
        expected_artifact="a.json",
        evidence_required=[],
        pass_condition=PassCondition(type="json_valid"),
        failure_condition="fc",
    )
    result = verify_task(task, tmp_path)
    jsonschema.validate(result.to_dict(), load_schema("verification.schema.json"))


SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"AKIA[0-9A-Z]{16}",  # AWS access key
        r"ghp_[A-Za-z0-9]{36}",  # GitHub token
        r"github_pat_[A-Za-z0-9_]{22,}",
        r"sk-[A-Za-z0-9]{32,}",  # API secret keys
        r"xox[baprs]-[A-Za-z0-9-]{10,}",  # Slack
        r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"apify_api_[A-Za-z0-9]{20,}",
    )
]

SCANNED_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".cfg", ".txt"}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "runs",
    "outputs",
    ".claude",
}


def test_no_secrets_in_repository() -> None:
    hits: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path}: {pattern.pattern}")
    assert not hits, f"possible secrets found: {hits}"


@pytest.mark.live
def test_live_fixture_layout_note() -> None:  # pragma: no cover - never runs in CI
    """Placeholder for optional live tests; excluded by default (-m 'not live')."""
    raise AssertionError("live tests must be explicitly opted into")
