"""Read-only repository access behind a protocol.

Mirrors the ``github_authority_audit`` data-source pattern:

- ``FixtureRepositorySource`` reads snapshot fixtures — the offline/CI path.
- ``LiveRepositorySource`` is a loud placeholder; live retrieval is performed by
  the Claude Code skill layer writing snapshots into a fixture directory, which
  this module then reads. Python never talks to model or network APIs, and CI
  never requires the network.

Fixture layout::

    <root>/
      owners/<owner>.json                     # ["repo-a", "repo-b", ...]
      repos/<owner>/<name>/metadata.json      # repository metadata mapping
      repos/<owner>/<name>/tree.json          # ["path/one", "path/two", ...]
      repos/<owner>/<name>/files.json         # {"path": "text content", ...}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from loop_engineering.domain.errors import LiveAccessUnavailable


class RepositorySource(Protocol):
    """Read-only access to a portfolio of repository snapshots."""

    def discover(self, owner: str) -> list[str]: ...

    def metadata(self, owner: str, name: str) -> dict[str, Any]: ...

    def tree(self, owner: str, name: str) -> list[str]: ...

    def files(self, owner: str, name: str) -> dict[str, str]: ...


class FixtureRepositorySource:
    """Reads repository snapshots from a fixture directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"fixture root does not exist: {self.root}")

    def _load(self, path: Path) -> Any:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _repo_dir(self, owner: str, name: str) -> Path:
        return self.root / "repos" / owner / name

    def discover(self, owner: str) -> list[str]:
        path = self.root / "owners" / f"{owner}.json"
        if not path.is_file():
            raise LiveAccessUnavailable(f"no owner index for {owner} at {path}")
        names = self._load(path)
        if not isinstance(names, list):
            raise ValueError(f"corrupt owner index: {path}")
        return [str(n) for n in names]

    def metadata(self, owner: str, name: str) -> dict[str, Any]:
        path = self._repo_dir(owner, name) / "metadata.json"
        if not path.is_file():
            raise LiveAccessUnavailable(f"no metadata snapshot for {owner}/{name} at {path}")
        data = self._load(path)
        if not isinstance(data, dict):
            raise ValueError(f"corrupt metadata fixture: {path}")
        return data

    def tree(self, owner: str, name: str) -> list[str]:
        path = self._repo_dir(owner, name) / "tree.json"
        if not path.is_file():
            raise LiveAccessUnavailable(f"no tree snapshot for {owner}/{name} at {path}")
        data = self._load(path)
        if not isinstance(data, list):
            raise ValueError(f"corrupt tree fixture: {path}")
        return [str(p) for p in data]

    def files(self, owner: str, name: str) -> dict[str, str]:
        path = self._repo_dir(owner, name) / "files.json"
        if not path.is_file():
            return {}
        data = self._load(path)
        if not isinstance(data, dict):
            raise ValueError(f"corrupt files fixture: {path}")
        return {str(k): str(v) for k, v in data.items()}


class LiveRepositorySource:
    """Loud placeholder: live GitHub access is not wired into this runtime."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or (
            "live GitHub access is not available in this execution environment; "
            "use the skill layer to fetch snapshots into a fixture directory and "
            "re-run against that fixture root"
        )

    def discover(self, owner: str) -> list[str]:
        raise LiveAccessUnavailable(self.reason)

    def metadata(self, owner: str, name: str) -> dict[str, Any]:
        raise LiveAccessUnavailable(self.reason)

    def tree(self, owner: str, name: str) -> list[str]:
        raise LiveAccessUnavailable(self.reason)

    def files(self, owner: str, name: str) -> dict[str, str]:
        raise LiveAccessUnavailable(self.reason)
