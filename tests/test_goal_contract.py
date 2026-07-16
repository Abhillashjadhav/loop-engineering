"""Canonical digest, immutability, amendments, schema validation."""

from __future__ import annotations

import pytest
from tests.conftest import make_contract_draft

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import ContractViolation


def test_canonical_digest_is_deterministic_and_order_independent() -> None:
    a = goal_contract.compute_digest(make_contract_draft())
    b = goal_contract.compute_digest(dict(reversed(list(make_contract_draft().items()))))
    assert a == b
    assert a.startswith("sha256:")


def test_lock_adds_digest_and_validates() -> None:
    locked = goal_contract.lock(make_contract_draft())
    assert locked["canonical_digest"] == goal_contract.compute_digest(locked)
    goal_contract.verify_integrity(locked)


def test_mutation_after_lock_is_detected() -> None:
    locked = goal_contract.lock(make_contract_draft())
    locked["goal_statement"] = "quietly different goal"
    with pytest.raises(ContractViolation, match="digest mismatch"):
        goal_contract.verify_integrity(locked)


def test_unlocked_contract_rejected() -> None:
    with pytest.raises(ContractViolation, match="not locked"):
        goal_contract.verify_integrity(make_contract_draft())


def test_schema_violation_rejected() -> None:
    bad = make_contract_draft()
    bad["goal_match_threshold"] = 250
    with pytest.raises(ContractViolation, match="schema violation"):
        goal_contract.lock(bad)


def test_amendment_creates_new_version_with_trail() -> None:
    v1 = goal_contract.lock(make_contract_draft())
    v2 = goal_contract.amend(
        v1, {"goal_statement": "amended goal"}, approved_by="abhillash", reason="scope shift"
    )
    assert v2["version"] == 2
    assert v2["amendments"][0]["previous_digest"] == v1["canonical_digest"]
    assert v1["goal_statement"] != v2["goal_statement"]
    goal_contract.verify_integrity(v2)
    # the original is untouched
    goal_contract.verify_integrity(v1)


def test_amendment_requires_approver_and_reason() -> None:
    v1 = goal_contract.lock(make_contract_draft())
    with pytest.raises(ContractViolation, match="approver"):
        goal_contract.amend(v1, {"goal_statement": "x"}, approved_by=" ", reason="r")
    with pytest.raises(ContractViolation, match="reason"):
        goal_contract.amend(v1, {"goal_statement": "x"}, approved_by="a", reason="")


def test_amendment_cannot_touch_protected_fields() -> None:
    v1 = goal_contract.lock(make_contract_draft())
    with pytest.raises(ContractViolation, match="not directly amendable"):
        goal_contract.amend(v1, {"canonical_digest": "sha256:0"}, "a", "r")


def test_save_and_load_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    locked = goal_contract.lock(make_contract_draft())
    path = tmp_path / "c.yaml"
    goal_contract.save(locked, path)
    loaded = goal_contract.load(path)
    assert loaded["canonical_digest"] == locked["canonical_digest"]
