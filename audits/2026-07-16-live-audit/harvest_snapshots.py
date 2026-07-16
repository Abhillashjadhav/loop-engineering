#!/usr/bin/env python3
"""Harvest public GitHub snapshots for the authority audit (run this from any
machine with normal GitHub access — it uses only unauthenticated public REST).

Usage:
    python harvest_snapshots.py --subjects ../../examples/subjects.yaml \
        --out snapshots/

Then, back in the Loop Engineering repo:
    loop-engineering audit-github --subjects examples/subjects.yaml \
        --fixtures audits/2026-07-16-live-audit/snapshots

Output layout (FixtureDataSource contract, see evals/README.md):
    snapshots/
    ├── profiles/<login>.json          # user profile snapshot
    ├── candidates/<slug>.json         # candidate login list per subject
    ├── repos/<login>/page-N.json      # complete paginated repo listing,
    │                                  # enriched with commit/contributor counts
    └── evidence/…                     # raw responses + sha256 + timestamps

NOTE on signals: this script harvests inventory + metadata. The per-repository
*observable signals* the rubric consumes (README claim backing, template
similarity, engineering-depth markers, …) are recorded afterwards by the
/loop-engineer skill layer inspecting each repository's content; repositories
without recorded signals are scored at low confidence and classified
INSUFFICIENT_EVIDENCE rather than guessed — never edit signals by hand.

Unauthenticated rate limit is 60 requests/hour; pass a token via
GITHUB_TOKEN to raise it (public_repo read scope is enough).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.github.com"


def _get(url: str) -> tuple[dict | list, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw), raw


def _save_evidence(out: Path, name: str, url: str, raw: str) -> dict:
    evidence_dir = out / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / name).write_text(raw, encoding="utf-8")
    return {
        "url": url,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "file": f"evidence/{name}",
    }


def _commit_count(owner: str, repo: str) -> int:
    # Cheap total-commit count: request one commit and read the last page number.
    url = f"{API}/repos/{owner}/{repo}/commits?per_page=1"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            link = resp.headers.get("Link", "")
            if 'rel="last"' in link:
                last = [part for part in link.split(",") if 'rel="last"' in part][0]
                return int(last.split("page=")[-1].split(">")[0].split("&")[0])
            return len(json.load(resp))
    except Exception:
        return 0


def _contributors(owner: str, repo: str) -> int:
    try:
        data, _ = _get(f"{API}/repos/{owner}/{repo}/contributors?per_page=100&anon=true")
        return len(data) if isinstance(data, list) else 1
    except Exception:
        return 1


def harvest_subject(subject: dict, out: Path) -> None:
    login = subject["candidate_login"]
    slug = subject["slug"]
    manifest: list[dict] = []

    profile, raw = _get(f"{API}/users/{login}")
    manifest.append(_save_evidence(out, f"{login}-profile.json", f"{API}/users/{login}", raw))
    (out / "profiles").mkdir(parents=True, exist_ok=True)
    (out / "profiles" / f"{login}.json").write_text(
        json.dumps(
            {
                "login": profile.get("login"),
                "name": profile.get("name"),
                "company": profile.get("company"),
                "blog": profile.get("blog"),
                "twitter": profile.get("twitter_username"),
                "location": profile.get("location"),
                "bio": profile.get("bio"),
                "followers": profile.get("followers"),
                "public_repos": profile.get("public_repos"),
                "evidence_links": [
                    {
                        "origin": "github_profile",
                        "url": profile.get("html_url", ""),
                        "excerpt": f"profile: {profile.get('name')}, {profile.get('blog')}",
                        "retrieved_at": datetime.now(UTC).isoformat(),
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (out / "candidates").mkdir(parents=True, exist_ok=True)
    (out / "candidates" / f"{slug}.json").write_text(json.dumps([login]), encoding="utf-8")

    page, total = 1, 0
    repo_dir = out / "repos" / login
    repo_dir.mkdir(parents=True, exist_ok=True)
    while True:
        url = f"{API}/users/{login}/repos?per_page=100&page={page}&type=owner&sort=full_name"
        listing, raw = _get(url)
        if not isinstance(listing, list) or not listing:
            break
        manifest.append(_save_evidence(out, f"{login}-repos-page-{page}.json", url, raw))
        enriched = []
        for r in listing:
            owner, name = login, r["name"]
            record = {
                "name": name,
                "fork": r.get("fork", False),
                "archived": r.get("archived", False),
                "mirror": bool(r.get("mirror_url")),
                "stargazers_count": r.get("stargazers_count", 0),
                "forks_count": r.get("forks_count", 0),
                "language": r.get("language"),
                "size": r.get("size", 0),
                "created_at": r.get("created_at", ""),
                "pushed_at": r.get("pushed_at", ""),
                "open_issues": r.get("open_issues_count", 0),
                "license": (r.get("license") or {}).get("spdx_id"),
                "dependencies_declared": False,  # inspected later by the skill layer
                "has_tests": False,  # inspected later by the skill layer
                "has_ci": False,  # inspected later by the skill layer
                "runnable_setup_documented": False,  # inspected later
                "pull_requests": 0,  # inspected later
                "releases": 0,  # inspected later (tags API)
                "contributors": 1 if r.get("fork") else _contributors(owner, name),
                "commit_count": 0 if r.get("fork") else _commit_count(owner, name),
                "signals": {},  # populated by the inspection stage, never by hand
            }
            enriched.append(record)
            total += 1
            time.sleep(0.2)
        (repo_dir / f"page-{page}.json").write_text(json.dumps(enriched, indent=2))
        page += 1

    expected = profile.get("public_repos")
    print(f"{login}: {total} repositories harvested (profile says public_repos={expected})")
    if expected is not None and total != expected:
        print(f"  WARNING: count mismatch — record this in unresolved uncertainties")
    (out / "evidence" / f"{login}-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def verify_snapshots(out: Path, subjects: list[dict]) -> int:
    """Validate a harvested snapshot dir loads through the engine's data source."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from loop_engineering.use_cases.github_authority_audit.datasource import FixtureDataSource
    from loop_engineering.use_cases.github_authority_audit.inventory import build_inventory

    ds = FixtureDataSource(out)
    failures = 0
    for subject in subjects:
        login, slug = subject["candidate_login"], subject["slug"]
        profile = ds.profile(login)
        for key in ("login", "name", "blog", "bio", "public_repos"):
            if key not in profile:
                print(f"FAIL {login}: profile missing {key!r}")
                failures += 1
        inventory = build_inventory(login, ds.repositories(login))
        counts = inventory.counts()
        expected = profile.get("public_repos")
        marker = "OK " if counts["total"] == expected else "MISMATCH"
        print(
            f"{marker} {slug}: {counts['total']} repos harvested "
            f"(profile public_repos={expected}) -> {counts}"
        )
        if counts["total"] != expected:
            failures += 1
        empty_signals = sum(1 for r in inventory.authored if not r.signals)
        if empty_signals:
            print(
                f"NOTE {slug}: {empty_signals} authored repo(s) have no recorded signals yet — "
                "they will classify INSUFFICIENT_EVIDENCE until the inspection stage runs"
            )
    print("verify:", "FAILED" if failures else "PASSED")
    return 1 if failures else 0


def self_test() -> int:
    """Prove the output layout satisfies the engine's FixtureDataSource contract
    without touching the network (stubbed API responses)."""
    import tempfile
    import unittest.mock as mock

    profile_stub = {
        "login": "stub-user",
        "name": "Stub User",
        "company": None,
        "blog": "https://stub.example",
        "twitter_username": "stub",
        "location": None,
        "bio": "stub bio",
        "followers": 1,
        "public_repos": 1,
        "html_url": "https://github.com/stub-user",
    }
    listing_stub = [
        {
            "name": "stub-repo",
            "fork": False,
            "archived": False,
            "mirror_url": None,
            "stargazers_count": 3,
            "forks_count": 1,
            "language": "Python",
            "size": 42,
            "created_at": "2026-01-01T00:00:00Z",
            "pushed_at": "2026-07-01T00:00:00Z",
            "open_issues_count": 0,
            "license": {"spdx_id": "MIT"},
        }
    ]
    responses = iter(
        [
            (profile_stub, json.dumps(profile_stub)),
            (listing_stub, json.dumps(listing_stub)),
            ([], "[]"),  # listing page 2 -> empty, ends pagination
            ([{"login": "stub-user"}], "[]"),  # contributors
        ]
    )
    with (
        tempfile.TemporaryDirectory() as tmp,
        mock.patch(f"{__name__}._get", side_effect=lambda url: next(responses)),
        mock.patch(f"{__name__}._commit_count", return_value=7),
        mock.patch(f"{__name__}._contributors", return_value=1),
        mock.patch(f"{__name__}.time") as faketime,
    ):
        faketime.sleep = lambda *_: None
        out = Path(tmp) / "snapshots"
        harvest_subject(
            {"candidate_login": "stub-user", "slug": "stub"},
            out,
        )
        rc = verify_snapshots(
            out, [{"candidate_login": "stub-user", "slug": "stub"}]
        )
        if rc == 0:
            record = json.loads((out / "repos" / "stub-user" / "page-1.json").read_text())[0]
            assert record["commit_count"] == 7 and record["license"] == "MIT"
            print("self-test: PASSED (layout satisfies FixtureDataSource contract)")
        return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects")
    ap.add_argument("--out", default="snapshots")
    ap.add_argument("--verify", action="store_true", help="validate an existing --out dir")
    ap.add_argument("--self-test", action="store_true", help="offline layout self-test")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.subjects:
        sys.exit("--subjects is required (except with --self-test)")
    try:
        import yaml  # type: ignore[import-untyped]

        subjects = yaml.safe_load(Path(args.subjects).read_text())["subjects"]
    except ModuleNotFoundError:
        sys.exit("pip install pyyaml first")
    out = Path(args.out)
    if args.verify:
        return verify_snapshots(out, subjects)
    for subject in subjects:
        harvest_subject(subject, out)
    print(f"done -> {out}/ ; next: signal inspection, then run with --fixtures {out}")
    return verify_snapshots(out, subjects)


if __name__ == "__main__":
    sys.exit(main())
