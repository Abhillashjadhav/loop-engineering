"""Stage-1 (M2) confidence audit — deterministic, offline, fixture-only.

Executes the broad scanner against the committed fixture portfolio and asserts
the twelve confidence checks: complete inventory, correct visibility/fork,
correct language/stack, correct README/docs/test/CI signals, security/dependency
signals, secret detected-but-fully-redacted, no private source leakage, healthy
signals not treated as risk, slop-wrapper risk signals WITHOUT any premature
AI-slop verdict, byte-identical repeated runs, fixture-backed evidence, and no
real GitHub access. This locks the properties into CI so later milestones cannot
silently regress them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_engineering.domain.errors import LiveAccessUnavailable
from loop_engineering.use_cases.portfolio_auditor import scanner as sc
from loop_engineering.use_cases.portfolio_auditor.datasource import (
    FixtureRepositorySource,
    LiveRepositorySource,
)
from loop_engineering.use_cases.portfolio_auditor.models import RepoVisibility

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "fixtures"
    / "portfolio_auditor"
    / "demo-portfolio"
)
NOW = "2026-07-17T00:00:00+00:00"

PLANTED_SECRETS = [
    "EXAMPLE_placeholder_secret_abcdef0123",
    "EXAMPLE_placeholder_billing_secret_0002",
    "aws_secret_FAKE_placeholder_0000",
]
# Private-repo source content that must never surface in scan output.
PRIVATE_SOURCE_MARKERS = ["def charge", "STRIPE_KEY", "return {'ok': True}"]

# Fields that only exist once a deep-inspection classifier does — must be ABSENT
# from the broad scan (no premature verdicts).
FORBIDDEN_VERDICT_TOKENS = ["AI_SLOP", '"verdict"', '"recommendation"', "ai_slop"]


def _source() -> FixtureRepositorySource:
    return FixtureRepositorySource(FIXTURE_ROOT)


def _portfolio_json() -> str:
    scans = sc.scan_portfolio(_source(), "acme", now=NOW)
    return json.dumps([s.to_dict() for s in scans], sort_keys=True)


def test_inventory_is_complete() -> None:
    scans = sc.scan_portfolio(_source(), "acme", now=NOW)
    assert [s.name for s in scans] == [
        "healthy-lib",
        "internal-service",
        "slop-wrapper",
        "stale-fork",
    ]


def test_visibility_and_fork_status_correct() -> None:
    scans = {s.name: s for s in sc.scan_portfolio(_source(), "acme", now=NOW)}
    assert scans["internal-service"].visibility is RepoVisibility.PRIVATE
    assert scans["healthy-lib"].visibility is RepoVisibility.PUBLIC
    assert scans["stale-fork"].freshness.is_fork and scans["stale-fork"].freshness.archived
    assert not scans["healthy-lib"].freshness.is_fork


def test_language_and_stack_correct() -> None:
    scans = {s.name: s for s in sc.scan_portfolio(_source(), "acme", now=NOW)}
    assert "python" in scans["healthy-lib"].stack
    assert "node" in scans["slop-wrapper"].stack
    assert "Python" in scans["internal-service"].languages


def test_readme_docs_test_ci_signals_correct() -> None:
    scans = {s.name: s for s in sc.scan_portfolio(_source(), "acme", now=NOW)}
    hl, sw = scans["healthy-lib"], scans["slop-wrapper"]
    assert hl.readme.has_install_section and hl.readme.has_usage_section
    assert hl.docs.has_license_file and hl.docs.has_contributing
    assert hl.tests_ci.has_tests and hl.tests_ci.has_ci
    assert not sw.tests_ci.has_tests and not sw.tests_ci.has_ci
    assert not sw.docs.has_license_file


def test_security_and_dependency_signals_detected() -> None:
    scans = {s.name: s for s in sc.scan_portfolio(_source(), "acme", now=NOW)}
    assert scans["healthy-lib"].security.has_lockfile
    assert scans["healthy-lib"].security.pinned_dependencies is True
    assert scans["slop-wrapper"].security.pinned_dependencies is False
    assert len(scans["slop-wrapper"].security.secret_hits) >= 2
    assert len(scans["internal-service"].security.secret_hits) >= 1


def test_secret_detected_but_fully_redacted_everywhere() -> None:
    blob = _portfolio_json()
    for secret in PLANTED_SECRETS:
        assert secret not in blob, f"secret leaked: {secret}"
    scans = sc.scan_portfolio(_source(), "acme", now=NOW)
    for s in scans:
        for hit in s.security.secret_hits:
            assert hit.redacted == "***REDACTED***"
            assert set(hit.to_dict()) == {"rule", "path", "line", "redacted"}


def test_no_private_source_content_leaks() -> None:
    private = next(
        s for s in sc.scan_portfolio(_source(), "acme", now=NOW) if s.name == "internal-service"
    )
    blob = json.dumps(private.to_dict())
    for marker in PRIVATE_SOURCE_MARKERS:
        assert marker not in blob, f"private source leaked: {marker}"


def test_healthy_signals_not_treated_as_risk() -> None:
    hl = next(s for s in sc.scan_portfolio(_source(), "acme", now=NOW) if s.name == "healthy-lib")
    assert hl.security.secret_hits == []
    assert hl.security.pinned_dependencies is True
    assert hl.tests_ci.has_tests and hl.tests_ci.has_ci
    assert hl.docs.has_license_file


def test_slop_wrapper_has_risk_signals_but_no_premature_verdict() -> None:
    sw = next(s for s in sc.scan_portfolio(_source(), "acme", now=NOW) if s.name == "slop-wrapper")
    # risk signals present
    assert {c.category for c in sw.mechanical_claims} >= {"production_readiness", "adoption"}
    assert sw.security.secret_hits and not sw.tests_ci.has_tests
    # but the broad scan issues NO verdict/classification
    blob = json.dumps(sw.to_dict())
    for token in FORBIDDEN_VERDICT_TOKENS:
        assert token not in blob, f"premature verdict token present: {token}"


def test_repeated_runs_are_byte_identical() -> None:
    assert _portfolio_json() == _portfolio_json()


def test_every_finding_points_to_fixture_backed_evidence() -> None:
    scans = sc.scan_portfolio(_source(), "acme", now=NOW)
    for s in scans:
        for hit in s.security.secret_hits:
            assert hit.path and hit.line >= 1
        for claim in s.mechanical_claims:
            assert claim.location and ":" in claim.location


def test_no_real_github_access() -> None:
    # The audit runs against fixtures only; the live source refuses to run.
    assert isinstance(_source(), FixtureRepositorySource)
    with pytest.raises(LiveAccessUnavailable):
        LiveRepositorySource().discover("acme")
