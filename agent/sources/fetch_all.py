"""Watchlist orchestrator — emits a URL fetch queue (no network).

ATS APIs (Greenhouse / Lever / Ashby) are DISABLED as of 2026-05-01:
direct datacenter HTTP and `web_fetch` both return HTTP 403 from the
Anthropic Routine sandbox. Manual dry run on 2026-04-29 confirmed
0/68 successful fetches with web_fetch and 0 control hosts reachable
either. Until a transport with permitted egress is wired up, this
script logs the disabled state and emits an empty queue.

The Python adapters (greenhouse.py / lever.py / ashby.py) are kept
intact — `build_urls` and `parse_response` are still good code, only
the orchestrator is paused.

Primary candidate source is now Indeed MCP (see CLAUDE.md Step 1d).
Secondary source is Gmail label reads (Step 1e). Workday and
proprietary career pages remain TODO.

Usage:
    python agent/sources/fetch_all.py --date 2026-05-02
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: pyyaml not installed. Run: pip install pyyaml\n")
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).parent))
import greenhouse  # noqa: E402,F401  (kept importable for future re-enable)
import lever  # noqa: E402,F401
import ashby  # noqa: E402,F401
import apify_linkedin  # noqa: E402
import gmail_linkedin  # noqa: E402


ATS_DISABLED = True
ATS_DISABLED_REASON = (
    "Greenhouse / Lever / Ashby APIs return HTTP 403 from Anthropic's "
    "Routine datacenter IP via web_fetch (confirmed 2026-04-29: "
    "0/68 fetches succeeded; control hosts also blocked). Re-enable once "
    "a transport with permitted egress is available."
)


def build_queue(watchlist_path: Path) -> dict:
    """Build the fetch queue.

    With ATS_DISABLED=True (current state), this counts the watchlist
    breakdown for the audit summary but emits an empty queue. Indeed and
    Gmail-label sources are handled by the agent directly per CLAUDE.md
    Steps 1d / 1e and do not flow through this script.
    """
    with watchlist_path.open() as f:
        config = yaml.safe_load(f)

    companies = config.get("companies", [])
    by_ats: dict[str, int] = {}
    for entry in companies:
        ats = entry.get("ats") or "unknown"
        by_ats[ats] = by_ats.get(ats, 0) + 1

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "ats_disabled": ATS_DISABLED,
        "ats_disabled_reason": ATS_DISABLED_REASON,
        "watchlist_size": len(companies),
        "watchlist_by_ats": by_ats,
        "queue_size": 0,
        "queue": [],
        "notes": [
            "ATS pipeline disabled. Primary source is Indeed MCP (CLAUDE.md Step 1d).",
            "Secondary source is Gmail labels (CLAUDE.md Step 1e).",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True,
                    help="Run date (YYYY-MM-DD); used in output path")
    ap.add_argument("--watchlist", type=Path,
                    default=Path("profile/target_companies.yaml"))
    ap.add_argument("--output-root", type=Path, default=Path("outputs"))
    args = ap.parse_args()

    if not args.watchlist.exists():
        print(f"ERROR: watchlist not found: {args.watchlist}", file=sys.stderr)
        return 1

    result = build_queue(args.watchlist)

    out_dir = args.output_root / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    queue_path = out_dir / "_fetch_queue.json"
    queue_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Pre-create the responses directory so the agent has somewhere to
    # write Indeed/Gmail per-source artifacts if it chooses to.
    (out_dir / "_fetch_responses").mkdir(parents=True, exist_ok=True)

    if ATS_DISABLED:
        print("ATS APIs disabled - 403 from datacenter IP")
        print(f"  watchlist={result['watchlist_size']} companies "
              f"({result['watchlist_by_ats']}); queue=0")
        print(f"  output: {queue_path}")

        # Apify LinkedIn runs alongside Indeed when ATS is disabled.
        # If the config is missing or the token is still the placeholder,
        # apify_linkedin.run_all_queries() returns [] after logging a
        # non-fatal warning to trajectory.jsonl. Indeed-only continues.
        try:
            linkedin_jobs = apify_linkedin.run_all_queries()
        except Exception as e:
            print(f"  apify-linkedin: skipped ({type(e).__name__}: {e})")
            linkedin_jobs = []

        if linkedin_jobs:
            raw_path = out_dir / "_raw_candidates.jsonl"
            with raw_path.open("a") as f:
                for job in linkedin_jobs:
                    f.write(json.dumps(job, ensure_ascii=False) + "\n")
            print(f"  apify-linkedin: {len(linkedin_jobs)} jobs appended to {raw_path}")
        else:
            print("  apify-linkedin: 0 jobs (placeholder token or disabled)")

        # Gmail LinkedIn / Naukri alerts (CLAUDE.md Step 1e). Reads any
        # thread JSON the agent has dumped to outputs/{date}/_gmail_threads/
        # via Gmail MCP. Missing files are non-fatal — returns 0 and continues.
        try:
            gmail_jobs = gmail_linkedin.fetch_jobs(args.date, root=".")
        except Exception as e:
            print(f"  gmail-alerts: skipped ({type(e).__name__}: {e})")
            gmail_jobs = []

        if gmail_jobs:
            raw_path = out_dir / "_raw_candidates.jsonl"
            with raw_path.open("a") as f:
                for job in gmail_jobs:
                    f.write(json.dumps(job, ensure_ascii=False) + "\n")
            by_src: dict[str, int] = {}
            for j in gmail_jobs:
                by_src[j.get("source", "?")] = by_src.get(j.get("source", "?"), 0) + 1
            print(f"  gmail-alerts: {len(gmail_jobs)} jobs ({by_src}) appended to {raw_path}")
        else:
            print("  gmail-alerts: 0 jobs (no _gmail_threads/*.json or no parseable subjects)")
    else:
        print(
            f"Built fetch queue: {result['queue_size']} URLs. "
            f"Output: {queue_path}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
