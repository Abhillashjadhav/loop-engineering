"""Versioned, canonical, digest-locked Goal Contract (spec §4).

The contract is immutable during a run. A change creates a new version (or a
recorded amendment that requires explicit user approval). The canonical digest
is a sha256 over the canonical JSON encoding of every field except the digest
itself.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from loop_engineering.domain.errors import ContractViolation
from loop_engineering.domain.models import utc_now

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "goal-contract.schema.json"

DIGEST_FIELD = "canonical_digest"


def _schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        loaded: dict[str, Any] = json.load(fh)
    return loaded


def canonical_json(data: dict[str, Any]) -> str:
    """Canonical encoding: sorted keys, compact separators, ensure_ascii."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_digest(contract: dict[str, Any]) -> str:
    """sha256 digest of the contract excluding the digest field itself."""
    body = {k: v for k, v in contract.items() if k != DIGEST_FIELD}
    return "sha256:" + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def lock(contract: dict[str, Any]) -> dict[str, Any]:
    """Return a locked copy carrying its canonical digest. Validates the schema."""
    locked = copy.deepcopy(contract)
    locked[DIGEST_FIELD] = compute_digest(locked)
    validate(locked)
    return locked


def validate(contract: dict[str, Any]) -> None:
    """Schema-validate; raise ContractViolation with the first error."""
    try:
        jsonschema.validate(contract, _schema())
    except jsonschema.ValidationError as exc:
        raise ContractViolation(f"goal contract schema violation: {exc.message}") from exc


def verify_integrity(contract: dict[str, Any]) -> None:
    """Raise ContractViolation if the stored digest does not match the content."""
    stored = contract.get(DIGEST_FIELD)
    if not stored:
        raise ContractViolation("contract is not locked (missing canonical_digest)")
    actual = compute_digest(contract)
    if stored != actual:
        raise ContractViolation(
            f"contract digest mismatch: stored {stored} != computed {actual}; "
            "the contract was mutated after locking"
        )


def amend(
    contract: dict[str, Any],
    changes: dict[str, Any],
    approved_by: str,
    reason: str,
) -> dict[str, Any]:
    """Create the next contract version. Requires explicit approver and reason.

    The original contract is untouched; the amendment trail records the
    previous digest so history is reconstructable.
    """
    if not approved_by.strip():
        raise ContractViolation("amendment requires an explicit approver")
    if not reason.strip():
        raise ContractViolation("amendment requires a recorded reason")
    verify_integrity(contract)
    forbidden = {DIGEST_FIELD, "version", "goal_id", "amendments"}
    illegal = forbidden.intersection(changes)
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
    """Load a locked contract from YAML/JSON and verify schema + digest."""
    p = Path(path)
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) if p.suffix in {".yaml", ".yml"} else json.load(fh)
    if not isinstance(data, dict):
        raise ContractViolation(f"{p} does not contain a contract mapping")
    validate(data)
    verify_integrity(data)
    return data


def load_unlocked(path: str | Path) -> dict[str, Any]:
    """Load a draft contract (no digest yet) for `init` to lock."""
    p = Path(path)
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) if p.suffix in {".yaml", ".yml"} else json.load(fh)
    if not isinstance(data, dict):
        raise ContractViolation(f"{p} does not contain a contract mapping")
    return data


def save(contract: dict[str, Any], path: str | Path) -> None:
    """Persist a locked contract (verifies integrity first)."""
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


def requirements(contract: dict[str, Any]) -> list[str]:
    """The goal requirements every task must map onto (the contract's scope).

    success_checks are verified by the loops and the E2E reviewer rather than
    mapped 1:1 onto tasks.
    """
    return [str(s) for s in contract.get("scope", [])]
