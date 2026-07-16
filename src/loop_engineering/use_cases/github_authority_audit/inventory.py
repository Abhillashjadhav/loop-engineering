"""Repository inventory (spec §10).

Distinguishes original repositories, forks, archived repos, mirrors, and
empty repos. Forks are excluded from authored-code scoring but reported
separately. Stars/forks are recorded as distribution signals only — never as
quality. Inaccessible or oversized content is recorded honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepoRecord:
    """Normalized snapshot of one repository."""

    name: str
    kind: str  # "original" | "fork" | "archived" | "mirror" | "empty"
    stars: int
    forks: int
    language: str | None
    size_kb: int
    created_at: str
    pushed_at: str
    contributors: int
    commit_count: int
    releases: int
    open_issues: int
    pull_requests: int
    has_tests: bool
    has_ci: bool
    dependencies_declared: bool
    license_name: str | None
    runnable_setup_documented: bool
    inaccessible: bool = False
    inaccessible_reason: str = ""
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "size_kb": self.size_kb,
            "created_at": self.created_at,
            "pushed_at": self.pushed_at,
            "contributors": self.contributors,
            "commit_count": self.commit_count,
            "releases": self.releases,
            "open_issues": self.open_issues,
            "pull_requests": self.pull_requests,
            "has_tests": self.has_tests,
            "has_ci": self.has_ci,
            "dependencies_declared": self.dependencies_declared,
            "license_name": self.license_name,
            "runnable_setup_documented": self.runnable_setup_documented,
            "inaccessible": self.inaccessible,
            "inaccessible_reason": self.inaccessible_reason,
            "signals": dict(self.signals),
        }


@dataclass
class Inventory:
    login: str
    records: list[RepoRecord]

    @property
    def originals(self) -> list[RepoRecord]:
        return [r for r in self.records if r.kind == "original" and not r.inaccessible]

    @property
    def authored(self) -> list[RepoRecord]:
        """Repos that count toward authored-code scoring: originals plus
        archived own work. Forks, mirrors, empty, and inaccessible are out."""
        return [
            r for r in self.records if r.kind in ("original", "archived") and not r.inaccessible
        ]

    @property
    def forks(self) -> list[RepoRecord]:
        return [r for r in self.records if r.kind == "fork"]

    @property
    def inaccessible(self) -> list[RepoRecord]:
        return [r for r in self.records if r.inaccessible]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.records:
            out[r.kind] = out.get(r.kind, 0) + 1
        out["inaccessible"] = len(self.inaccessible)
        out["total"] = len(self.records)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "counts": self.counts(),
            "records": [r.to_dict() for r in self.records],
        }


def classify_kind(raw: dict[str, Any]) -> str:
    if raw.get("kind") in {"original", "fork", "archived", "mirror", "empty"}:
        # Round-trip of an already-normalized record: the kind is authoritative.
        return str(raw["kind"])
    if raw.get("fork"):
        return "fork"
    if raw.get("mirror_url") or raw.get("mirror"):
        return "mirror"
    if raw.get("archived"):
        return "archived"
    if int(raw.get("size", raw.get("size_kb", 0))) == 0 or int(raw.get("commit_count", 0)) == 0:
        return "empty"
    return "original"


def build_inventory(login: str, raw_repos: list[dict[str, Any]]) -> Inventory:
    records: list[RepoRecord] = []
    for raw in raw_repos:
        records.append(
            RepoRecord(
                name=str(raw.get("name", "?")),
                kind=classify_kind(raw),
                stars=int(raw.get("stargazers_count", raw.get("stars", 0))),
                forks=int(raw.get("forks_count", raw.get("forks", 0))),
                language=raw.get("language"),
                size_kb=int(raw.get("size", raw.get("size_kb", 0))),
                created_at=str(raw.get("created_at", "")),
                pushed_at=str(raw.get("pushed_at", "")),
                contributors=int(raw.get("contributors", 1)),
                commit_count=int(raw.get("commit_count", 0)),
                releases=int(raw.get("releases", 0)),
                open_issues=int(raw.get("open_issues", 0)),
                pull_requests=int(raw.get("pull_requests", 0)),
                has_tests=bool(raw.get("has_tests", False)),
                has_ci=bool(raw.get("has_ci", False)),
                dependencies_declared=bool(raw.get("dependencies_declared", False)),
                license_name=raw.get("license", raw.get("license_name")),
                runnable_setup_documented=bool(raw.get("runnable_setup_documented", False)),
                inaccessible=bool(raw.get("inaccessible", False)),
                inaccessible_reason=str(raw.get("inaccessible_reason", "")),
                signals=dict(raw.get("signals", {})),
            )
        )
    return Inventory(login=login, records=records)
