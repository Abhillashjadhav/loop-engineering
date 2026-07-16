"""Lever postings adapter.

Lever exposes every customer board at:
    https://api.lever.co/v0/postings/{slug}?mode=json

This module is I/O-only: it does NOT make network calls. The agent
fetches the URLs returned by `build_urls` via its `web_fetch` tool,
and `parse_response` converts each JSON response into Job objects.

Usage:
    python agent/sources/lever.py --slug shopify --print-url
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse the Job dataclass from greenhouse module
sys.path.insert(0, str(Path(__file__).parent))
from greenhouse import Job  # noqa: E402


LEVER_API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def build_urls(slugs: list[str]) -> list[tuple[str, str]]:
    """Return [(slug, url), ...] for the agent to fetch via web_fetch."""
    return [(slug, LEVER_API.format(slug=slug)) for slug in slugs]


def parse_response(slug: str, json_text: str,
                   company_name: str | None = None) -> list[Job]:
    """Parse a Lever API response into Job objects."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    company = company_name or slug
    jobs: list[Job] = []
    for p in data:
        cats = p.get("categories") or {}
        loc = cats.get("location", "")
        team = cats.get("team")
        jobs.append(Job(
            source="lever",
            company=company,
            title=p.get("text", "").strip(),
            location=loc.strip() if isinstance(loc, str) else "",
            url=p.get("hostedUrl", "").strip(),
            posted_at=None,  # Lever returns createdAt as epoch ms; can convert if needed
            raw_id=p.get("id"),
            department=team,
            description_excerpt=(p.get("descriptionPlain") or "")[:500] or None,
        ))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser(description="Lever adapter (no network)")
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
