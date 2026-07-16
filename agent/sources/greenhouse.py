"""Greenhouse boards adapter.

Greenhouse exposes every customer board at:
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs

This module is I/O-only: it does NOT make network calls. It exposes
`build_urls` to produce the list of URLs the agent should fetch via
its `web_fetch` tool, and `parse_response` to convert a JSON response
body into `Job` objects. Direct datacenter HTTP is blocked upstream;
all fetching is delegated to the agent.

Usage:
    python agent/sources/greenhouse.py --slug anthropic --print-url
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict


GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


@dataclass
class Job:
    source: str          # "greenhouse" | "lever" | "ashby" | "indeed" | "gmail"
    company: str
    title: str
    location: str
    url: str              # canonical apply URL
    posted_at: str | None  # ISO date if available
    raw_id: str | None     # ATS-side ID for dedupe
    department: str | None = None
    description_excerpt: str | None = None  # first ~500 chars, for filter pass

    def to_dict(self) -> dict:
        return asdict(self)


def build_urls(slugs: list[str]) -> list[tuple[str, str]]:
    """Return [(slug, url), ...] for the agent to fetch via web_fetch."""
    return [(slug, GREENHOUSE_API.format(slug=slug)) for slug in slugs]


def parse_response(slug: str, json_text: str,
                   company_name: str | None = None) -> list[Job]:
    """Parse a Greenhouse API response into Job objects.

    Returns an empty list if the response is missing, malformed, or has
    no jobs. Never raises on bad input — the agent decides retry policy.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    jobs_raw = data.get("jobs", [])
    company = company_name or slug

    jobs: list[Job] = []
    for j in jobs_raw:
        # Greenhouse returns location.name as a free-text string
        loc = (j.get("location") or {}).get("name") or ""
        # departments is a list; take primary
        depts = j.get("departments") or []
        dept = depts[0].get("name") if depts and isinstance(depts[0], dict) else None
        jobs.append(Job(
            source="greenhouse",
            company=company,
            title=j.get("title", "").strip(),
            location=loc.strip(),
            url=j.get("absolute_url", "").strip(),
            posted_at=j.get("updated_at"),
            raw_id=str(j.get("id")) if j.get("id") is not None else None,
            department=dept,
            description_excerpt=None,
        ))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="Greenhouse adapter (no network)")
    ap.add_argument("--slug", required=True, help="Greenhouse company slug")
    ap.add_argument("--print-url", action="store_true",
                    help="Print the URL the agent should fetch via web_fetch")
    ap.add_argument("--parse-file", type=str,
                    help="Parse a saved JSON response file from disk")
    ap.add_argument("--company", help="Display name (defaults to slug)")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if args.print_url:
        for slug, url in build_urls([args.slug]):
            print(f"{slug}\t{url}")
        return 0

    if args.parse_file:
        json_text = open(args.parse_file).read()
        jobs = parse_response(args.slug, json_text, args.company)
        out = [j.to_dict() for j in jobs]
        json.dump(out, sys.stdout, indent=2 if args.pretty else None, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    print("ERROR: pass --print-url or --parse-file=<path>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
