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


def _is_git_ignored(path: Path, root: Path, as_dir: bool = False) -> bool:
    """True if git would ignore ``path`` (so it can hold private content).

    ``as_dir`` appends a trailing slash so directory-only gitignore patterns
    (``/config/private/``) match even when the directory does not exist yet —
    git cannot infer directory-ness for absent paths, so a fresh checkout
    (where private dirs are never committed, hence never present) would
    otherwise fail the boundary check spuriously.
    """
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return False
    candidate = str(rel) + ("/" if as_dir else "")
    result = subprocess.run(
        ["git", "check-ignore", "-q", candidate],
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
    # Non-existent paths (fresh checkout, read-only lookups) are checked as
    # the file itself and as the parent DIRECTORY (trailing slash) so
    # dir-only ignore patterns still match; a missing boundary still raises.
    ignored = _is_git_ignored(target, base) or _is_git_ignored(target.parent, base, as_dir=True)
    if not ignored:
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
