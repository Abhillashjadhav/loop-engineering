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
import math
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from loop_engineering.domain.errors import ContractViolation
from loop_engineering.domain.models import utc_now

DIGEST_FIELD = "canonical_digest"


def _schema() -> dict[str, Any]:
    with (
        files("loop_engineering")
        .joinpath("schemas", "goal-contract.schema.json")
        .open(encoding="utf-8") as fh
    ):
        loaded: dict[str, Any] = json.load(fh)
    return loaded


def canonical_json(data: dict[str, Any]) -> str:
    """Canonical encoding: sorted keys, compact separators, ensure_ascii."""
    _require_json_domain(data, "goal contract")
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _require_json_domain(value: Any, label: str) -> None:
    """Reject YAML-only types and aliases with cycles; never coerce contract values."""

    active: set[int] = set()
    pending: list[tuple[Any, bool]] = [(value, False)]
    while pending:
        item, leaving = pending.pop()
        if leaving:
            active.remove(id(item))
            continue
        if item is None or type(item) in (str, int, bool):
            continue
        if type(item) is float:
            if not math.isfinite(item):
                raise ContractViolation(f"{label} contains a non-finite number")
            continue
        if not isinstance(item, (dict, list)):
            raise ContractViolation(
                f"{label} contains a value outside the JSON contract domain: {type(item).__name__}"
            )
        if id(item) in active:
            raise ContractViolation(f"{label} contains a recursive YAML alias")
        active.add(id(item))
        pending.append((item, True))
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ContractViolation(f"{label} contains a non-string mapping key")
            pending.extend((child, False) for child in item.values())
        else:
            pending.extend((child, False) for child in item)


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
    data = _read_contract(p, "locked contract")
    if not isinstance(data, dict):
        raise ContractViolation(f"{p} does not contain a contract mapping")
    validate(data)
    verify_integrity(data)
    return data


def load_unlocked(path: str | Path) -> dict[str, Any]:
    """Load a draft contract (no digest yet) for `init` to lock."""
    p = Path(path)
    data = _read_contract(p, "goal")
    if not isinstance(data, dict):
        raise ContractViolation(f"{p} does not contain a contract mapping")
    return data


def _read_contract(path: Path, role: str) -> Any:
    """Translate only file and parser failures, leaving validation defects visible."""
    kind = "YAML" if path.suffix in {".yaml", ".yml"} else "JSON"
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) if kind == "YAML" else json.load(fh)
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise ContractViolation(f"cannot read {role} file {path}: {reason}") from exc
    except UnicodeError as exc:
        raise ContractViolation(f"{role} file {path} is not valid UTF-8") from exc
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ContractViolation(f"{role} file {path} has invalid {kind} syntax") from exc
    _require_json_domain(data, f"{role} file {path}")
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
