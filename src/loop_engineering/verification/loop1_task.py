"""Loop 1 — Atomic Task Verification (spec §6).

Runs after every task. The verifier works only from the task definition and
the filesystem: the executor's statement is never used as proof, and the
executor role may never verify its own work.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from loop_engineering.domain.errors import SelfVerificationError
from loop_engineering.domain.models import (
    CheckResult,
    PassCondition,
    Task,
    VerificationResult,
    utc_now,
)

EXECUTOR_ROLE = "executor"
VERIFIER_ROLE = "task-verifier"


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _eval_pass_condition(cond: PassCondition, artifact: Path, run_directory: Path) -> CheckResult:
    name = f"pass_condition:{cond.type}"
    target = artifact if cond.path is None else (run_directory / cond.path)
    if cond.type == "file_exists":
        return CheckResult(name, target.is_file(), str(target))
    if not target.is_file():
        return CheckResult(name, False, f"target missing: {target}")
    if cond.type == "file_contains":
        text = target.read_text(encoding="utf-8", errors="replace")
        ok = cond.text is not None and cond.text in text
        return CheckResult(name, ok, f"looking for {cond.text!r}")
    if cond.type in ("json_valid", "json_has_keys", "min_count"):
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return CheckResult(name, False, f"invalid JSON: {exc}")
        if cond.type == "json_valid":
            return CheckResult(name, True, "valid JSON")
        if cond.type == "json_has_keys":
            if not isinstance(data, dict):
                return CheckResult(name, False, "JSON root is not an object")
            missing = [k for k in cond.keys if k not in data]
            return CheckResult(name, not missing, f"missing keys: {missing}" if missing else "")
        # min_count
        value = data.get(cond.count_key) if isinstance(data, dict) else data
        count = len(value) if isinstance(value, (list, dict)) else None
        ok = count is not None and cond.min is not None and count >= cond.min
        return CheckResult(name, ok, f"count={count}, min={cond.min}")
    if cond.type == "digest_matches":
        actual = file_digest(target)
        return CheckResult(name, actual == cond.digest, f"actual={actual}")
    return CheckResult(name, False, f"unknown pass condition type: {cond.type}")


def verify_task(
    task: Task,
    run_directory: str | Path,
    executor_role: str = EXECUTOR_ROLE,
    verifier_role: str = VERIFIER_ROLE,
) -> VerificationResult:
    """Independently verify one executed task against the filesystem."""
    if verifier_role == executor_role:
        raise SelfVerificationError(
            f"role {executor_role!r} may not verify its own work on task {task.task_id}"
        )
    run_dir = Path(run_directory)
    artifact = run_dir / "artifacts" / task.expected_artifact
    checks: list[CheckResult] = []

    checks.append(CheckResult("artifact_exists", artifact.is_file(), str(artifact)))

    checks.append(_eval_pass_condition(task.pass_condition, artifact, run_dir))

    missing_evidence = [
        rel for rel in task.evidence_required if not (run_dir / "evidence" / rel).is_file()
    ]
    checks.append(
        CheckResult(
            "evidence_present",
            not missing_evidence,
            f"missing: {missing_evidence}" if missing_evidence else "",
        )
    )

    # Scope: the artifact must live inside the run's artifacts/ tree.
    try:
        artifact.resolve().relative_to((run_dir / "artifacts").resolve())
        in_scope = True
    except ValueError:
        in_scope = False
    checks.append(CheckResult("artifact_within_scope", in_scope, str(artifact)))

    digest = file_digest(artifact) if artifact.is_file() else None
    checks.append(CheckResult("output_digest_recorded", digest is not None, digest or "no file"))

    passed = all(c.passed for c in checks)
    result = VerificationResult(
        verification_id=f"v1-{task.task_id}-{uuid.uuid4().hex[:8]}",
        loop="loop1_task",
        subject_id=task.task_id,
        verifier_role=verifier_role,
        executor_role=executor_role,
        passed=passed,
        checks=checks,
        artifact_digest=digest,
        failure_reason=None
        if passed
        else "; ".join(f"{c.name}: {c.detail}" for c in checks if not c.passed),
        verified_at=utc_now(),
    )
    if passed:
        task.artifact_digest = digest
    return result
