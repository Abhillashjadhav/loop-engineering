"""Repo-wide secret scan (schema-conformance tests join as schemas land)."""

from __future__ import annotations

import re

import pytest
from tests.conftest import REPO_ROOT

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
