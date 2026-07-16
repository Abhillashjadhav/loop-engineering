"""GitHub data access behind a protocol.

- FixtureDataSource: synthetic JSON fixtures — the offline/CI path.
- LiveDataSource: placeholder that fails loudly. Live retrieval must be done
  by the Claude Code skill layer (WebFetch/GitHub tooling) writing fetched
  snapshots into a fixture directory, which this module then reads. Python
  never talks to model APIs, and CI never requires the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from loop_engineering.domain.errors import LiveAccessUnavailable


class GitHubDataSource(Protocol):
    """Read-only access to public profile + repository snapshots."""

    def profile(self, login: str) -> dict[str, Any]: ...

    def candidate_profiles(self, subject_name: str) -> list[dict[str, Any]]: ...

    def repositories(self, login: str) -> list[dict[str, Any]]: ...


class FixtureDataSource:
    """Reads snapshots from a fixture directory:

    fixtures/
    ├── profiles/<login>.json          # one candidate profile per login
    ├── candidates/<subject-slug>.json # candidate login list per subject
    └── repos/<login>/page-<n>.json    # paged repository lists
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"fixture root does not exist: {self.root}")

    def _load(self, path: Path) -> Any:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def profile(self, login: str) -> dict[str, Any]:
        path = self.root / "profiles" / f"{login}.json"
        if not path.is_file():
            raise LiveAccessUnavailable(f"no profile snapshot for {login} at {path}")
        data = self._load(path)
        if not isinstance(data, dict):
            raise ValueError(f"corrupt profile fixture: {path}")
        return data

    def candidate_profiles(self, subject_slug: str) -> list[dict[str, Any]]:
        path = self.root / "candidates" / f"{subject_slug}.json"
        if not path.is_file():
            return []
        logins = self._load(path)
        if not isinstance(logins, list):
            raise ValueError(f"corrupt candidates fixture: {path}")
        return [self.profile(str(login)) for login in logins]

    def repositories(self, login: str) -> list[dict[str, Any]]:
        """All pages, concatenated — mirrors the 'retrieve all pages' rule."""
        directory = self.root / "repos" / login
        if not directory.is_dir():
            raise LiveAccessUnavailable(f"no repository snapshots for {login} at {directory}")
        repos: list[dict[str, Any]] = []
        for page in sorted(directory.glob("page-*.json")):
            chunk = self._load(page)
            if not isinstance(chunk, list):
                raise ValueError(f"corrupt repo page fixture: {page}")
            repos.extend(d for d in chunk if isinstance(d, dict))
        return repos


class LiveDataSource:
    """Loud placeholder: live GitHub access is not wired in this runtime."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or (
            "live GitHub access is not available in this execution environment; "
            "use the /loop-engineer skill layer to fetch public snapshots into a "
            "fixture directory and re-run with --fixtures"
        )

    def profile(self, login: str) -> dict[str, Any]:
        raise LiveAccessUnavailable(self.reason)

    def candidate_profiles(self, subject_slug: str) -> list[dict[str, Any]]:
        raise LiveAccessUnavailable(self.reason)

    def repositories(self, login: str) -> list[dict[str, Any]]:
        raise LiveAccessUnavailable(self.reason)
