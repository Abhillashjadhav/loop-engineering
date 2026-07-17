"""Privacy boundary: no personal content on tracked paths (fail closed)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loop_engineering.use_cases.personal_chief_of_staff.privacy import (
    PrivacyViolation,
    assert_no_private_paths_tracked,
    private_path,
    repo_root,
)


def test_no_private_paths_are_tracked_in_repo() -> None:
    assert assert_no_private_paths_tracked() == [], "planted failure: private data committed to git"


def test_private_path_rejects_non_private_target() -> None:
    with pytest.raises(PrivacyViolation):
        private_path("src/loop_engineering/leak.json")


def test_private_path_rejects_escape() -> None:
    with pytest.raises(PrivacyViolation):
        private_path("data/private/../../escape.json")


def test_private_path_accepts_private_root(tmp_path: Path) -> None:
    # Simulate a repo with the private boundary ignored.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("/data/private/\n", encoding="utf-8")
    p = private_path("data/private/brief.json", root=tmp_path)
    assert p.parent.is_dir()
    assert str(p).endswith("data/private/brief.json")


def test_private_path_fails_closed_when_boundary_missing(tmp_path: Path) -> None:
    # No .gitignore entry → the path is NOT ignored → must refuse to write.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("# no private entry\n", encoding="utf-8")
    with pytest.raises(PrivacyViolation):
        private_path("data/private/brief.json", root=tmp_path)


def test_repo_root_finds_git_dir() -> None:
    assert (repo_root() / ".git").exists()
