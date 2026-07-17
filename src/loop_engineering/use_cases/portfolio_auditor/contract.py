"""Immutable, digest-locked ProductDecisionContract for the Portfolio Auditor.

This module deliberately *reuses* the Loop Engineering candidate-freezing
mechanism (``contracts.goal_contract``: canonical JSON, sha256 digest,
integrity verification) instead of duplicating it. It adds only what is
auditor-specific: the contract JSON Schema, a loader for the shipped locked
instance, and typed accessors for the locked policies that later milestones
consume (AI-slop policy, business-accuracy scale, recommendation verdicts,
auto-merge gates and forbidden actions).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from loop_engineering.contracts.goal_contract import (
    DIGEST_FIELD,
    canonical_json,
    compute_digest,
    verify_integrity,
)
from loop_engineering.domain.errors import ContractViolation
from loop_engineering.domain.models import utc_now

__all__ = [
    "DIGEST_FIELD",
    "ai_slop_policy",
    "ai_slop_verdicts",
    "amend",
    "assessment_dimensions",
    "auto_merge_forbidden_actions",
    "auto_merge_required_gates",
    "business_accuracy_scale",
    "canonical_json",
    "compute_digest",
    "load",
    "load_default",
    "load_unlocked",
    "lock",
    "prioritization",
    "recommendation_verdicts",
    "save",
    "validate",
    "verify_integrity",
]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "portfolio-auditor-contract.schema.json"
_DEFAULT_CONTRACT_PATH = _REPO_ROOT / "use_cases" / "portfolio-auditor" / "contract.yaml"

_FORBIDDEN_AMENDMENT_FIELDS = frozenset({DIGEST_FIELD, "version", "contract_id", "amendments"})


def _schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        loaded: dict[str, Any] = json.load(fh)
    return loaded


def validate(contract: dict[str, Any]) -> None:
    """Schema-validate the contract; raise ContractViolation on the first error."""
    try:
        jsonschema.validate(contract, _schema())
    except jsonschema.ValidationError as exc:
        msg = f"portfolio-auditor contract schema violation: {exc.message}"
        raise ContractViolation(msg) from exc


def lock(contract: dict[str, Any]) -> dict[str, Any]:
    """Return a locked copy carrying its canonical digest (schema-validated)."""
    locked = copy.deepcopy(contract)
    locked[DIGEST_FIELD] = compute_digest(locked)
    validate(locked)
    return locked


def amend(
    contract: dict[str, Any],
    changes: dict[str, Any],
    approved_by: str,
    reason: str,
) -> dict[str, Any]:
    """Create the next contract version — explicit approver + reason required.

    Structural fields (id, version, digest, amendment trail) are never directly
    amendable. The original contract is left untouched; the amendment trail
    records the previous digest so history stays reconstructable.
    """
    if not approved_by.strip():
        raise ContractViolation("amendment requires an explicit approver")
    if not reason.strip():
        raise ContractViolation("amendment requires a recorded reason")
    verify_integrity(contract)
    illegal = _FORBIDDEN_AMENDMENT_FIELDS.intersection(changes)
    if illegal:
        raise ContractViolation(f"fields not directly amendable: {sorted(illegal)}")

    amended = copy.deepcopy(contract)
    amended.update(copy.deepcopy(changes))
    amended["version"] = int(contract["version"]) + 1
    trail = list(contract.get("amendments", []))
    trail.append(
        {
            "amended_at": utc_now(),
            "approved_by": approved_by,
            "reason": reason,
            "previous_digest": contract[DIGEST_FIELD],
        }
    )
    amended["amendments"] = trail
    return lock(amended)


def load(path: str | Path) -> dict[str, Any]:
    """Load a locked contract and verify both schema and digest integrity."""
    data = _read(path)
    validate(data)
    verify_integrity(data)
    return data


def load_unlocked(path: str | Path) -> dict[str, Any]:
    """Load a draft contract (no digest yet)."""
    return _read(path)


def load_default() -> dict[str, Any]:
    """Load the shipped, locked Portfolio Auditor contract."""
    return load(_DEFAULT_CONTRACT_PATH)


def save(contract: dict[str, Any], path: str | Path) -> None:
    """Persist a locked contract via atomic replacement (integrity-checked)."""
    verify_integrity(contract)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        if p.suffix in {".yaml", ".yml"}:
            yaml.safe_dump(contract, fh, sort_keys=False, allow_unicode=False)
        else:
            json.dump(contract, fh, indent=2)
    tmp.replace(p)


def _read(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) if p.suffix in {".yaml", ".yml"} else json.load(fh)
    if not isinstance(data, dict):
        raise ContractViolation(f"{p} does not contain a contract mapping")
    return data


# --- typed policy accessors (single read points for later milestones) ------


def ai_slop_policy(contract: dict[str, Any]) -> dict[str, Any]:
    policy: dict[str, Any] = dict(contract["ai_slop_policy"])
    return policy


def ai_slop_verdicts(contract: dict[str, Any]) -> list[str]:
    return [str(v) for v in contract["ai_slop_policy"]["verdicts"]]


def business_accuracy_scale(contract: dict[str, Any]) -> list[str]:
    return [str(v) for v in contract["business_accuracy"]["scale"]]


def recommendation_verdicts(contract: dict[str, Any]) -> list[str]:
    return [str(v) for v in contract["recommendation_verdicts"]]


def assessment_dimensions(contract: dict[str, Any]) -> list[str]:
    return [str(d["key"]) for d in contract["assessment_dimensions"]]


def auto_merge_required_gates(contract: dict[str, Any]) -> list[str]:
    return [str(g["id"]) for g in contract["remediation_policy"]["auto_merge_required_gates"]]


def auto_merge_forbidden_actions(contract: dict[str, Any]) -> list[str]:
    return [str(a) for a in contract["remediation_policy"]["forbidden_auto_merge_actions"]]


def prioritization(contract: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(contract["prioritization"])
    return result
