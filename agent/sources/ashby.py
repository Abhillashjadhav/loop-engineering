"""Ashby job-board adapter.

Ashby exposes every customer board at:
    https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true

This module is I/O-only: it does NOT make network calls. The agent
fetches the URLs returned by `build_urls` via its `web_fetch` tool,
and `parse_response` converts each JSON response into Job objects.

Usage:
    python agent/sources/ashby.py --slug linear --print-url
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from greenhouse import Job  # noqa: E402


ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def build_urls(slugs: list[str]) -> list[tuple[str, str]]:
    """Return [(slug, url), ...] for the agent to fetch via web_fetch."""
    return [(slug, ASHBY_API.format(slug=slug)) for slug in slugs]


def parse_response(slug: str, json_text: str,
                   company_name: str | None = None) -> list[Job]:
    """Parse an Ashby API response into Job objects."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    company = company_name or data.get("name") or slug
    postings = data.get("jobs", [])

    jobs: list[Job] = []
    for p in postings:
        loc = p.get("location") or ""
        if isinstance(loc, dict):
            loc = loc.get("name", "")
        team = p.get("team") or p.get("department")
        jobs.append(Job(
            source="ashby",
            company=company,
            title=p.get("title", "").strip(),
            location=str(loc).strip(),
            url=p.get("jobUrl") or p.get("applyUrl", ""),
            posted_at=p.get("publishedAt"),
            raw_id=p.get("id"),
            department=team,
            description_excerpt=None,
        ))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="Ashby adapter (no network)")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--print-url", action="store_true")
    ap.add_argument("--parse-file", type=str)
    ap.add_argument("--company")
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
