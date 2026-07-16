"""Apify LinkedIn jobs source.

LinkedIn doesn't expose a public jobs API and direct scraping is blocked
from the Routine datacenter IP. The Apify actor `valig/linkedin-jobs-scraper`
runs on Apify's residential infrastructure and returns structured job
listings via the run-sync endpoint.

Actor input schema (verified 2026-05-11 via JSON view in Apify console):
    title:           string (one role per call, e.g. "Director Product AI")
    location:        string (e.g. "India", "Bengaluru")
    datePosted:      string code — "r604800" = past 7 days,
                     "r2592000" = past 30 days
    experienceLevel: array of code strings —
                     "1"=internship, "2"=entry, "3"=associate/mid-senior,
                     "4"=director, "5"=executive/VP, "6"=senior-executive
    contractType:    array — "F"=full-time, "P"=part-time, "C"=contract,
                     "T"=temporary
    remote:          array — "1"=on-site, "2"=remote, "3"=hybrid
    limit:           integer max results per call
    companyName:     array of company strings (optional)
    companyId:       array of LinkedIn company IDs (optional)

Output schema matches `agent/sources/greenhouse.py:Job` so survivors merge
cleanly into `outputs/{date}/_raw_candidates.jsonl` with
`source="linkedin_apify"`.

Pricing: $0.40 per 1,000 results (pay-per-result, not compute-time). At
5 queries × 50 results = 250 results/day = ~$0.10/day = $3/month, well
within Apify's $5/month free credit.

Usage (programmatic):
    from agent.sources.apify_linkedin import run_all_queries
    jobs = run_all_queries()
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


CONFIG_PATH = Path(__file__).resolve().parent.parent / "secrets" / "apify_config.json"
TRAJECTORY_PATH = Path("outputs") / "trajectory.jsonl"
PLACEHOLDER_TOKEN = "REPLACE_WITH_ACTUAL_TOKEN"
TOKEN_ENV_VAR = "APIFY_TOKEN"

# Actor is configurable via APIFY_ACTOR env var (defaults to valig/linkedin-jobs-scraper).
# Verified alternatives (input schemas differ — test before swapping):
#   - bebity/linkedin-jobs-scraper       (richer fields: recruiter, applicant count)
#   - apimaestro/linkedin-jobs-scraper-no-cookies (broader catalog, no auth)
# To swap in production: set APIFY_ACTOR secret to e.g. "bebity~linkedin-jobs-scraper".
# The actor's input schema is unchanged — if you swap, also verify the new
# actor accepts {title, location, limit, datePosted, experienceLevel}.
DEFAULT_ACTOR = "valig~linkedin-jobs-scraper"
ACTOR_ENV_VAR = "APIFY_ACTOR"


def _actor_url() -> str:
    actor = os.environ.get(ACTOR_ENV_VAR, DEFAULT_ACTOR).strip() or DEFAULT_ACTOR
    return f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"

# Date posted codes per the actor's input schema (verified 2026-05-11).
# These are LinkedIn's own filter values, passed verbatim as the actor's
# `datePosted` field.
DATE_PAST_24H = "r86400"         # 24 hours in seconds
DATE_PAST_48H = "r172800"        # 48 hours in seconds
DATE_PAST_WEEK = "r604800"       # 7 days in seconds
DATE_PAST_MONTH = "r2592000"     # 30 days in seconds

# Exhaustive daily-sweep defaults (chosen 2026-06-18, fixed same day). The agent
# runs daily, so a 24h window fully covers each day's new senior-PM India
# postings with no gap — and it's the right size: small, complete, cheap.
# IMPORTANT: the actor's `datePosted` only accepts LinkedIn's preset codes
# (r86400 / r604800 / r2592000). A non-preset like r172800 (48h) is REJECTED by
# the actor and makes EVERY query return 0 — which is what broke run #57. Keep
# date_posted to a value in VALID_DATE_POSTED; the run_query guard enforces it.
DEFAULT_DATE_POSTED = DATE_PAST_24H
DEFAULT_PER_QUERY_LIMIT = 300
VALID_DATE_POSTED = {DATE_PAST_24H, DATE_PAST_WEEK, DATE_PAST_MONTH}

# Senior-band filter: Mid-Senior (3) + Director (4) + Executive/VP (5).
# Excludes junior levels (1, 2) and very-senior CEO/board (6).
EXPERIENCE_SENIOR_BAND = ["3", "4", "5"]

# 24 strategic (title, location) tuples per CLAUDE.md Step 1d spec.
# Covers Director/Principal/GPM/Head/VP titles across India + 3 metros,
# plus Senior/Staff PM at premium-company seniority bands (often
# Principal-equivalent compensation at Google L6 / Databricks Staff /
# Stripe Sr — surfaced because LinkedIn doesn't filter by band).
# Cost: 24 queries × ~30 results × $0.40/1k ≈ $0.30/run = ~$9/month at
# daily cadence. Within Apify $5/month free credit only on alternating
# days — accept a small Apify bill (~$4/mo) for full LinkedIn coverage.
LINKEDIN_QUERIES: list[tuple[str, str]] = [
    # Broad catch-all net (added 2026-06-18). With experienceLevel = Mid-Senior
    # /Director/Exec (the >8yr band), a bare "Product Manager" query is the
    # exhaustive sweep — it returns EVERY senior PM posting in the 48h window,
    # including titles the narrow keyword queries below miss (e.g. "Senior
    # Manager, AI Product Management", the Boeing-class roles). The focused
    # queries that follow add ranking recall for AI/GenAI/Platform roles.
    ("Product Manager", "India"),
    ("Product Manager", "Bengaluru"),
    ("Product Manager", "Mumbai"),
    ("Product Manager", "Hyderabad"),
    ("Product Management", "India"),
    ("Senior Manager Product", "India"),
    # Director / Principal / Group / Head / VP — across India + metros
    ("Director Product Manager", "India"),
    ("Director Product Manager", "Bengaluru"),
    ("Director Product Manager", "Mumbai"),
    ("Director Product Manager", "Hyderabad"),
    # LinkedIn's canonical format ("of") that the algo indexes differently
    # from "Director Product Manager" — adds coverage for roles the user
    # finds manually (Google GPM, JLL Director PM, etc. were missed by the
    # "Director Product Manager" query but appear in "Director of Product
    # Management" saved searches). Fix applied 2026-06-17.
    ("Director of Product Management", "India"),
    ("Director of Product Management", "Bengaluru"),
    ("Director of Product Management", "Mumbai"),
    ("Principal Product Manager", "India"),
    ("Principal Product Manager", "Bengaluru"),
    ("Principal Product Manager", "Mumbai"),
    ("Group Product Manager", "India"),
    ("Group Product Manager", "Bengaluru"),
    ("Head of Product", "India"),
    ("Head of Product", "Bengaluru"),
    ("VP Product Management", "India"),
    # Senior / Staff PM — premium-company titles (Google L6, Databricks Staff,
    # Stripe Sr, Notion Staff) that the scorer + watchlist filter for fit.
    ("Senior Product Manager", "India"),
    ("Senior Product Manager", "Bengaluru"),
    ("Sr Product Manager", "India"),
    ("Staff Product Manager", "India"),
    ("Staff Product Manager", "Bengaluru"),
    # AI / GenAI / Platform / Agentic focus areas
    ("Director Product AI", "India"),
    ("Principal Product Manager AI", "India"),
    ("Principal Product Manager GenAI", "Bengaluru"),
    ("Director Product Platform", "India"),
    ("Principal Product Manager LLM", "India"),
    ("Director PM Agentic AI", "India"),
    ("Principal PM Developer Productivity", "Bengaluru"),
    # GPM / Head of Product — explicit phrasing for LinkedIn's algorithm
    ("Group Product Manager AI", "India"),
    ("Head of Product AI", "Bengaluru"),
]

# Top 30 target companies for company-name targeting mode.
# These are split into batches of 5 and passed as `companyName` arrays to
# the actor, which narrows results to roles posted by those employers.
# This catches roles at high-value companies that keyword queries miss
# (e.g. a role titled "Senior PM, AI Platform" at Stripe that wouldn't
# surface under "Director Product AI" but is Principal-equivalent comp).
WATCHLIST_COMPANIES: list[str] = [
    "Google", "Microsoft", "Meta", "Stripe", "Salesforce", "Adobe",
    "Atlassian", "Dropbox", "Twilio", "Snowflake", "Databricks", "Confluent",
    "Harness", "HashiCorp", "DataStax", "Elastic", "Grafana", "Sentry",
    "MSD", "Merck", "SAP", "Oracle", "ServiceNow", "Workday",
    "Teradata", "FICO", "Avaya", "Genesys", "NICE", "Verint",
]

_WATCHLIST_BATCH_SIZE = 5


@dataclass
class Job:
    """Mirrors agent/sources/greenhouse.py:Job for downstream compatibility."""
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: str | None
    raw_id: str | None
    department: str | None = None
    description_excerpt: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _log_trajectory(record: dict) -> None:
    """Append a JSON line to outputs/trajectory.jsonl. Best-effort, never raises."""
    try:
        TRAJECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRAJECTORY_PATH.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Trajectory logging must never break the run.
        pass


def load_config(path: Path | None = None) -> dict | None:
    """Return resolved config (token + actor + budget + memory), or None."""
    if path is None:
        path = CONFIG_PATH  # read module-level var at call time so monkeypatching works
    if not path.exists():
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "warning": f"apify_config.json missing at {path}",
            "decision": "skip_apify",
        })
        return None
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "warning": f"apify_config.json malformed: {e}",
            "decision": "skip_apify",
        })
        return None

    env_token = (os.environ.get(TOKEN_ENV_VAR) or "").strip()
    file_token = (config.get("apify_token") or "").strip()

    if env_token:
        token = env_token
    elif file_token and file_token != PLACEHOLDER_TOKEN:
        token = file_token
    else:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "warning": (
                f"no real token: {TOKEN_ENV_VAR} env var unset and "
                f"apify_config.json carries placeholder — set the GitHub "
                f"repo secret APIFY_TOKEN"
            ),
            "decision": "skip_apify",
        })
        return None

    resolved = dict(config)
    resolved["apify_token"] = token
    return resolved


def run_query(title: str, location: str, max_rows: int = DEFAULT_PER_QUERY_LIMIT,
              config: dict | None = None,
              company_names: list[str] | None = None) -> list[dict]:
    """Fire a single Apify run-sync call and return raw dataset items.

    Sends the actor's verified input schema (2026-05-11):
        {title, location, limit, datePosted, experienceLevel}

    Optionally includes `companyName` array when `company_names` is provided
    (used by run_company_watchlist_queries).

    Returns an empty list on any failure. Per-query failures are non-fatal
    — caller continues with the next query.
    """
    if config is None:
        config = load_config()
    if config is None:
        return []
    if requests is None:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "warning": "requests not installed",
            "decision": "skip_apify",
        })
        return []

    token = config["apify_token"]
    memory_mb = config.get("memory_mb", 128)
    params = {"token": token, "memory": memory_mb}

    # Verified actor input schema (Apify console JSON view, 2026-05-11):
    #   title (str), location (str), datePosted (str code), limit (int),
    #   experienceLevel (array of code strings).
    # `rows` is NOT a valid key for this actor — must be `limit`.
    # `datePosted: "Past Week"` is NOT valid — must be `r604800` (seconds).
    # Guard: the actor rejects non-preset datePosted codes (e.g. 48h/r172800),
    # which silently zeroes every query. Force a valid preset.
    date_posted = config.get("date_posted", DEFAULT_DATE_POSTED)
    if date_posted not in VALID_DATE_POSTED:
        date_posted = DEFAULT_DATE_POSTED
    payload: dict = {
        "title": title,
        "location": location,
        "limit": max_rows,
        "datePosted": date_posted,
        "experienceLevel": EXPERIENCE_SENIOR_BAND,
    }
    if company_names:
        payload["companyName"] = company_names

    query_label = f"{title} | {location}"
    if company_names:
        query_label += f" | companies={company_names}"

    try:
        resp = requests.post(_actor_url(), params=params, json=payload, timeout=180)
    except Exception as e:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "query": query_label,
            "warning": f"network error: {type(e).__name__}: {e}",
            "decision": "skip_query_continue",
        })
        return []

    if resp.status_code >= 400:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "query": query_label,
            "warning": f"http {resp.status_code}: {resp.text[:200]}",
            "decision": "skip_query_continue",
        })
        return []

    try:
        items = resp.json()
    except ValueError as e:
        _log_trajectory({
            "step": "1g",
            "source": "linkedin_apify",
            "query": query_label,
            "warning": f"json decode error: {e}",
            "decision": "skip_query_continue",
        })
        return []

    if not isinstance(items, list):
        return []
    return items


def parse_response(raw_items: list[dict], title: str, location: str,
                   source: str = "linkedin_apify") -> list[Job]:
    """Convert Apify dataset items into Job dataclass instances."""
    jobs: list[Job] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        company_name = (
            item.get("companyName")
            or item.get("company")
            or ""
        )
        job_title = item.get("title") or item.get("jobTitle") or ""
        job_loc = item.get("location") or location
        url = (
            item.get("link")
            or item.get("jobUrl")
            or item.get("url")
            or ""
        )
        posted = item.get("postedAt") or item.get("postedDate") or item.get("postedTimeAgo")
        raw_id = item.get("id") or item.get("jobId")
        description = item.get("descriptionText") or item.get("description") or ""
        if isinstance(description, str) and len(description) > 500:
            description = description[:500]

        jobs.append(Job(
            source=source,
            company=str(company_name).strip(),
            title=str(job_title).strip(),
            location=str(job_loc).strip(),
            url=str(url).strip(),
            posted_at=str(posted) if posted is not None else None,
            raw_id=str(raw_id) if raw_id is not None else None,
            department=None,
            description_excerpt=description or None,
        ))
    return jobs


def run_urls(urls: list[str], config: dict | None = None) -> list[dict]:
    """URL-targeted mode — DISABLED.

    valig/linkedin-jobs-scraper does NOT support per-URL targeting. Passing
    `linkedinUrls` causes the actor to ignore the key and run a default
    broad search, consuming budget on irrelevant roles. Verified on
    2026-05-11 run #3: 118 URLs in, 500 random items out, all dropped by
    title filter.

    Kept as a no-op stub for backwards-compat with callers in run_daily.py.
    """
    return []


def run_company_watchlist_queries(
    token: str,
    date: str,
    output_dir: Path,
    budget_cap: int = 300,
) -> list[dict]:
    """Query Apify actor for roles at WATCHLIST_COMPANIES (batches of 5).

    Uses the actor's `companyName` array input to target specific employers
    rather than broad keyword search. Catches roles at high-value companies
    that keyword queries miss — e.g. "Senior PM, AI Platform" at Stripe
    (Principal-equivalent comp but non-matching title keyword).

    Args:
        token:      Apify API token (resolved by caller from env / config).
        date:       Run date string (YYYY-MM-DD) used for output filenames.
        output_dir: Directory for per-batch raw JSON files.
        budget_cap: Max total rows across all batches (default 300).

    Returns:
        Aggregated list of Job dicts with source="linkedin_apify_watchlist".
        Per-batch failures are non-fatal — logged to trajectory and skipped.
    """
    if requests is None:
        _log_trajectory({
            "step": "1g-watchlist",
            "source": "linkedin_apify_watchlist",
            "warning": "requests not installed",
            "decision": "skip_watchlist",
        })
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build config dict the same shape load_config() would return so we can
    # reuse run_query() without refactoring its signature.
    cfg = {
        "apify_token": token,
        "memory_mb": 128,
        "max_jobs_per_run": budget_cap,
    }

    # Split WATCHLIST_COMPANIES into batches of _WATCHLIST_BATCH_SIZE.
    batches: list[list[str]] = [
        WATCHLIST_COMPANIES[i: i + _WATCHLIST_BATCH_SIZE]
        for i in range(0, len(WATCHLIST_COMPANIES), _WATCHLIST_BATCH_SIZE)
    ]

    aggregated: list[dict] = []

    for batch_idx, company_batch in enumerate(batches):
        if len(aggregated) >= budget_cap:
            _log_trajectory({
                "step": "1g-watchlist",
                "source": "linkedin_apify_watchlist",
                "warning": f"budget cap {budget_cap} reached at batch {batch_idx}",
                "decision": "stop_remaining_batches",
            })
            break

        per_batch_room = budget_cap - len(aggregated)
        max_rows = min(50, per_batch_room)

        _log_trajectory({
            "step": "1g-watchlist",
            "intent": f"query batch {batch_idx} companies={company_batch}",
            "batch_idx": batch_idx,
            "companies": company_batch,
        })

        raw_items = run_query(
            title="Product Manager",
            location="India",
            max_rows=max_rows,
            config=cfg,
            company_names=company_batch,
        )

        # Save raw batch response for auditability.
        batch_file = output_dir / f"company_watchlist_{batch_idx}.json"
        try:
            batch_file.write_text(
                json.dumps(raw_items, ensure_ascii=False, indent=2)
            )
        except OSError as e:
            _log_trajectory({
                "step": "1g-watchlist",
                "batch_idx": batch_idx,
                "warning": f"could not write batch file {batch_file}: {e}",
                "decision": "continue",
            })

        jobs = parse_response(
            raw_items,
            title="Product Manager",
            location="India",
            source="linkedin_apify_watchlist",
        )

        if len(aggregated) + len(jobs) > budget_cap:
            jobs = jobs[: budget_cap - len(aggregated)]

        aggregated.extend(j.to_dict() for j in jobs)

        _log_trajectory({
            "step": "1g-watchlist-batch",
            "batch_idx": batch_idx,
            "companies": company_batch,
            "raw_items": len(raw_items),
            "parsed_jobs": len(jobs),
            "running_total": len(aggregated),
        })

    _log_trajectory({
        "step": "1g-watchlist-complete",
        "source": "linkedin_apify_watchlist",
        "total_jobs": len(aggregated),
        "batches_run": len(batches),
    })

    return aggregated


def run_all_queries(config: dict | None = None,
                    queries: list[tuple[str, str]] | None = None,
                    include_watchlist: bool = False,
                    date: str = "",
                    output_dir: Path | None = None) -> list[dict]:
    """Iterate LINKEDIN_QUERIES and aggregate Job dicts.

    Args:
        config:            Resolved config dict (loaded from file/env if None).
        queries:           Override query list (uses LINKEDIN_QUERIES if None).
        include_watchlist: When True, also runs run_company_watchlist_queries()
                           against WATCHLIST_COMPANIES after keyword queries.
                           Default False to preserve existing caller behaviour.
        date:              Run date string (YYYY-MM-DD); used for watchlist
                           output filenames. Ignored when include_watchlist=False.
        output_dir:        Directory for watchlist batch JSON files. Defaults to
                           outputs/{date}/_apify_responses/ if not provided.
    """
    if config is None:
        config = load_config()
    if config is None:
        return []

    budget = int(config.get("max_jobs_per_run", 250))
    per_query_limit = int(config.get("per_query_limit", DEFAULT_PER_QUERY_LIMIT))
    queries = queries if queries is not None else LINKEDIN_QUERIES
    aggregated: list[dict] = []

    for title, location in queries:
        if len(aggregated) >= budget:
            _log_trajectory({
                "step": "1g",
                "source": "linkedin_apify",
                "warning": f"budget cap {budget} reached; stopping",
                "decision": "stop_remaining_queries",
            })
            break
        per_query_room = budget - len(aggregated)
        # Deep pagination per query (was hardcoded to 50 — the sampling cap that
        # limited the whole sweep to ~300 rows). With a 48h window each query's
        # result set is small and complete, so per_query_limit just needs to
        # clear a day's volume.
        max_rows = min(per_query_limit, per_query_room)
        raw_items = run_query(title, location, max_rows=max_rows, config=config)
        jobs = parse_response(raw_items, title, location)
        if len(aggregated) + len(jobs) > budget:
            jobs = jobs[: budget - len(aggregated)]
        aggregated.extend(j.to_dict() for j in jobs)
        _log_trajectory({
            "step": "1g-query",
            "query": f"{title} | {location}",
            "raw_items": len(raw_items),
            "parsed_jobs": len(jobs),
            "running_total": len(aggregated),
        })

    if include_watchlist and len(aggregated) < budget:
        watchlist_budget = budget - len(aggregated)
        resolved_output_dir = output_dir or Path("outputs") / date / "_apify_responses"
        watchlist_jobs = run_company_watchlist_queries(
            token=config["apify_token"],
            date=date,
            output_dir=resolved_output_dir,
            budget_cap=watchlist_budget,
        )
        aggregated.extend(watchlist_jobs)
        _log_trajectory({
            "step": "1g-watchlist-merged",
            "watchlist_jobs_added": len(watchlist_jobs),
            "grand_total": len(aggregated),
        })

    return aggregated


def main() -> int:
    """CLI entry point — useful for manual smoke-testing."""
    jobs = run_all_queries()
    json.dump(jobs, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"# {len(jobs)} jobs aggregated from LinkedIn via Apify",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
