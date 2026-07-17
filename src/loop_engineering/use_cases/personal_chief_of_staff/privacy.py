"""Private-data boundary guard.

All personal content lives under ignored directories (``data/private/``,
``runs/private/``, ``config/private/``). This module is the single place that
resolves private paths and asserts they are git-ignored, so the runtime can
never write personal content to a tracked path. Fail-closed: if a requested
private path escapes the private roots, it raises rather than writing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PRIVATE_ROOTS = ("data/private", "runs/private", "config/private")


class PrivacyViolation(RuntimeError):
    """Raised when a write would place personal content on a tracked path."""


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    return here


def _is_git_ignored(path: Path, root: Path) -> bool:
    """True if git would ignore ``path`` (so it can hold private content)."""
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(rel)],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def private_path(relative: str, *, root: Path | None = None, ensure_parent: bool = True) -> Path:
    """Resolve a path under a private root, asserting it is git-ignored.

    ``relative`` must start with one of the PRIVATE_ROOTS. Raises
    PrivacyViolation if the path escapes the private roots or is not ignored.
    """
    base = root or repo_root()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise PrivacyViolation(f"private path must be repo-relative and contained: {relative!r}")
    if not any(str(rel).replace("\\", "/").startswith(pr) for pr in PRIVATE_ROOTS):
        raise PrivacyViolation(
            f"path {relative!r} is not under a private root {PRIVATE_ROOTS}; "
            "personal content may only be written to ignored private directories"
        )
    target = (base / rel).resolve()
    target.relative_to(base.resolve())  # containment check
    if ensure_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    # Assert the boundary really is ignored (fail closed if .gitignore drifted).
    check = target if target.exists() else target.parent
    if not _is_git_ignored(check, base):
        raise PrivacyViolation(
            f"private root for {relative!r} is not git-ignored — refusing to write "
            "personal content to a tracked path; restore the .gitignore boundary"
        )
    return target


def assert_no_private_paths_tracked(root: Path | None = None) -> list[str]:
    """Return any tracked files that fall under the private roots (should be []).

    Used by tests and the privacy check to prove no personal content was
    staged/committed.
    """
    base = root or repo_root()
    tracked = subprocess.run(
        ["git", "ls-files", *PRIVATE_ROOTS],
        cwd=base,
        capture_output=True,
        text=True,
    )
    return [line for line in tracked.stdout.splitlines() if line.strip()]
