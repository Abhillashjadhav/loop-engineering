"""Identity verification: >= 2 attributes, collisions block, URLs prove nothing."""

from __future__ import annotations

import json

import pytest
from tests.conftest import GITHUB_FIXTURES

from loop_engineering.domain.errors import IdentityUnresolved
from loop_engineering.use_cases.github_authority_audit.identity import verify_identity


def load_profile(login: str) -> dict:  # type: ignore[type-arg]
    return json.loads((GITHUB_FIXTURES / "profiles" / f"{login}.json").read_text())


def test_confirmed_with_multiple_attributes() -> None:
    result = verify_identity(
        subject="Sam Builder",
        candidate_login="synthetic-builder",
        expected_attributes={
            "name": "Sam Builder",
            "blog": "sambuilder.dev",
            "twitter": "sam_builds",
        },
        profile=load_profile("synthetic-builder"),
    )
    assert result.confirmed
    assert len(result.matched_attributes) >= 2
    assert result.confidence >= 70


def test_single_attribute_is_not_enough() -> None:
    with pytest.raises(IdentityUnresolved, match="2 required"):
        verify_identity(
            subject="Sam Builder",
            candidate_login="weak-match",
            expected_attributes={
                "name": "Sam Builder",
                "blog": "sambuilder.dev",
                "twitter": "sam_builds",
            },
            profile=load_profile("weak-match"),
        )


def test_collision_blocks_analysis() -> None:
    with pytest.raises(IdentityUnresolved, match="collides"):
        verify_identity(
            subject="Alex Doe",
            candidate_login="ambiguous-a",
            expected_attributes={"name": "Alex Doe", "company": "Globex", "blog": "alexdoe"},
            profile=load_profile("ambiguous-a"),
            other_candidates=[load_profile("ambiguous-b")],
        )


def test_url_alone_proves_nothing() -> None:
    # No expected attributes supplied: even a plausible-looking login must not confirm.
    with pytest.raises(IdentityUnresolved):
        verify_identity(
            subject="Sam Builder",
            candidate_login="synthetic-builder",
            expected_attributes={},
            profile=load_profile("synthetic-builder"),
        )
