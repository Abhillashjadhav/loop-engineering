"""Milestone 2 — broad, read-only repository scanner over deterministic fixtures.

The scanner never talks to the network; it reads snapshot fixtures (mocked
GitHub data) and derives *mechanical* signals only. Secret values are never
emitted — only a redacted rule/location record.
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

# Planted secrets that must NEVER appear in scanner output. Deliberately NOT in
# any real-provider format (no Stripe live-key shape, no AWS access-key shape) so they neither
# trip the repo-wide real-secret scan nor GitHub push protection, yet still match
# the auditor's name/assignment-based detector rules.
PLANTED_SECRETS = [
    "EXAMPLE_placeholder_secret_abcdef0123",
    "EXAMPLE_placeholder_billing_secret_0002",
    "aws_secret_FAKE_placeholder_0000",
]


def source() -> FixtureRepositorySource:
    return FixtureRepositorySource(FIXTURE_ROOT)


def test_discover_lists_all_repos() -> None:
    assert set(source().discover("acme")) == {
        "healthy-lib",
        "slop-wrapper",
        "stale-fork",
        "internal-service",
    }


def test_scan_portfolio_scans_every_repo() -> None:
    scans = sc.scan_portfolio(source(), "acme", now=NOW)
    assert {s.name for s in scans} == {
        "healthy-lib",
        "slop-wrapper",
        "stale-fork",
        "internal-service",
    }
    # Deterministic ordering (by name) for reproducible reports.
    assert [s.name for s in scans] == sorted(s.name for s in scans)


def test_healthy_lib_signals() -> None:
    s = sc.scan_repository(source(), "acme", "healthy-lib", now=NOW)
    assert s.visibility is RepoVisibility.PUBLIC
    assert s.tests_ci.has_tests and s.tests_ci.test_file_count >= 3
    assert s.tests_ci.has_ci and s.tests_ci.ci_workflow_count == 1
    assert s.readme.has_readme
    assert s.readme.has_install_section and s.readme.has_usage_section
    assert s.readme.has_badges
    assert s.docs.has_license_file and s.docs.has_contributing
    assert "python" in s.stack
    assert "Python" in s.languages
    assert s.security.has_lockfile
    assert s.security.secret_hits == []
    assert s.packaging.has_pyproject_or_setup
    assert any("pip install" in c for c in s.packaging.install_commands)
    assert s.freshness.days_since_pushed == 7
    assert not s.freshness.is_fork and not s.freshness.archived


def test_slop_wrapper_secret_detection_and_redaction() -> None:
    s = sc.scan_repository(source(), "acme", "slop-wrapper", now=NOW)
    assert len(s.security.secret_hits) >= 2
    blob = json.dumps(s.to_dict())
    for secret in PLANTED_SECRETS:
        assert secret not in blob
    for hit in s.security.secret_hits:
        assert hit.redacted == "***REDACTED***"
        assert hit.path and hit.rule
    assert not s.tests_ci.has_tests
    assert not s.tests_ci.has_ci
    assert s.docs.has_license_file is False


def test_slop_wrapper_mechanical_claims() -> None:
    s = sc.scan_repository(source(), "acme", "slop-wrapper", now=NOW)
    cats = {c.category for c in s.mechanical_claims}
    assert "production_readiness" in cats
    assert "metric" in cats
    assert "adoption" in cats
    assert all(c.location for c in s.mechanical_claims)
    # unpinned dependencies noticed
    assert s.security.pinned_dependencies is False


def test_stale_fork_flags() -> None:
    s = sc.scan_repository(source(), "acme", "stale-fork", now=NOW)
    assert s.freshness.is_fork and s.freshness.archived
    assert s.freshness.days_since_pushed is not None and s.freshness.days_since_pushed > 900


def test_private_visibility_recorded_and_secret_redacted() -> None:
    s = sc.scan_repository(source(), "acme", "internal-service", now=NOW)
    assert s.visibility is RepoVisibility.PRIVATE
    assert len(s.security.secret_hits) >= 1
    assert "EXAMPLE_placeholder_billing_secret_0002" not in json.dumps(s.to_dict())
    assert "requirements.txt" in s.security.dependency_manifests
    assert s.security.declared_dependency_count == 3


def test_reposcan_round_trips() -> None:
    s = sc.scan_repository(source(), "acme", "healthy-lib", now=NOW)
    assert sc.RepoScan.from_dict(s.to_dict()) == s


def test_now_none_gives_no_freshness_age() -> None:
    s = sc.scan_repository(source(), "acme", "healthy-lib", now=None)
    assert s.freshness.days_since_pushed is None


def test_scan_records_provenance() -> None:
    s = sc.scan_repository(source(), "acme", "healthy-lib", now=NOW)
    d = s.to_dict()
    assert d["scanner_version"] == sc.SCANNER_VERSION
    assert d["owner"] == "acme" and d["name"] == "healthy-lib"


def test_live_source_raises_loudly() -> None:
    src = LiveRepositorySource()
    with pytest.raises(LiveAccessUnavailable):
        src.discover("acme")
    with pytest.raises(LiveAccessUnavailable):
        src.metadata("acme", "x")


def test_missing_repo_raises() -> None:
    with pytest.raises(LiveAccessUnavailable):
        sc.scan_repository(source(), "acme", "does-not-exist", now=NOW)


def test_pinned_deps_not_fooled_by_x_named_packages() -> None:
    # Regression (M2 review, blocking): package names containing x/X (lxml,
    # sphinx, openpyxl) must not flip a fully-pinned repo to unpinned.
    count, pinned = sc._dependency_signals(
        {"requirements.txt": "flask==3.0.0\nlxml==4.9.0\nopenpyxl==3.1.0\nsphinx==7.0.0\n"}
    )
    assert count == 4
    assert pinned is True
    # A real range still reads as unpinned.
    _, pinned2 = sc._dependency_signals({"requirements.txt": "flask==3.0.0\nrequests>=2.31\n"})
    assert pinned2 is False


def test_install_commands_capture_python_m_pip() -> None:
    readme = "# x\n\n## Install\n\n```bash\npython -m pip install foo\n```\n"
    assert any("python -m pip install" in c for c in sc._install_commands(readme))


def test_days_since_handles_naive_now_gracefully() -> None:
    # naive `now` vs aware pushed_at must degrade to None, not raise.
    assert sc._days_since("2026-07-17", "2026-07-10T00:00:00+00:00") is None
    assert sc._days_since("2026-07-17T00:00:00+00:00", "2026-07-10T00:00:00+00:00") == 7


def test_key_named_secret_assignment_detected_and_redacted() -> None:
    hits = sc.detect_secrets({"config.js": "awsKey: 'aws_secret_FAKE_placeholder_0000'\n"})
    assert any(h.rule == "key_named_assignment" for h in hits)
    for h in hits:
        assert h.redacted == "***REDACTED***"
    # slop-wrapper's planted awsKey is now detected (previously missed).
    scan = sc.scan_repository(source(), "acme", "slop-wrapper", now=NOW)
    assert any(h.path == "config.js" for h in scan.security.secret_hits)


def test_detect_secrets_covers_aws_and_stripe_rules() -> None:
    # Strings are constructed at runtime (split literals) so the repo-wide
    # real-secret scan never sees a contiguous AKIA/sk key in this file.
    aws = "AK" + "IA1234567890ABCDEF"
    stripe = "sk_" + "live_0123456789abcdef0123"
    hits = sc.detect_secrets({"c.py": f"a = '{aws}'\nb = '{stripe}'\n"})
    rules = {h.rule for h in hits}
    assert "aws_access_key_id" in rules
    assert "stripe_secret_key" in rules
    # values never stored on the hit
    for h in hits:
        assert h.redacted == "***REDACTED***"
