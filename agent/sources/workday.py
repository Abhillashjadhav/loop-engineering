"""Live HTTP fetcher for Workday-hosted public career sites.

Workday powers the careers pages of a large slice of big enterprises
(Boeing, NVIDIA, Salesforce, Dell, ...) that are invisible to the
Greenhouse/Lever/Ashby sweep. Each Workday tenant exposes a public,
no-auth JSON search endpoint:

    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets":{}, "limit":20, "offset":0, "searchText":"Product"}

Response shape:
    {"total": N, "jobPostings": [
        {"title": "...", "externalPath": "/job/.../R-123",
         "locationsText": "Bengaluru, India", "postedOn": "Posted 3 Days Ago",
         "bulletFields": ["R-123", ...]}, ...]}

It's free and returns every open posting per tenant; coverage is purely a
function of how many tenants are in the registry. The registry lives in
`data/workday_tenants.json` (not hardcoded) so the discovery probe can append
new employers without a code change — the "seed + grow" model.

This module mirrors greenhouse_fetch.py: per-tenant failures are non-fatal,
so a wrong slug or a tenant that blocks us just yields 0 jobs and a log line
rather than killing the run.

Usage (programmatic):
    from agent.sources.workday import fetch_all_jobs
    jobs = fetch_all_jobs()

CLI:
    python agent/sources/workday.py                 # fetch, print jobs JSON
    python agent/sources/workday.py --verify        # probe every tenant slug
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


# Registry file — repo-root relative. Resolved from this file's location so it
# works regardless of cwd (run_daily.py runs from agent/, CLI from repo root).
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "workday_tenants.json"

CXS_JOBS = "https://{host}/wday/cxs/{tenant}/{site}/jobs"

# Server-side search term. Workday matches it across the posting, so "Product"
# captures Director/Principal/GPM/Head/VP Product roles while keeping each pull
# bounded and relevant. The downstream title regex narrows further. Kept broad
# (not "Product Manager") so "Head of Product" / "Product Management" survive.
DEFAULT_SEARCH = "Product"

PAGE_SIZE = 20            # Workday's max per page for the cxs endpoint
MAX_PAGES_PER_TENANT = 8  # safety cap: 8 * 20 = 160 postings/tenant (plenty after PM filter)
LOCALE = "en-US"


def load_registry(path: Path | None = None) -> list[dict]:
    """Load the Workday tenant registry. Returns [] if the file is missing
    or malformed (non-fatal — caller continues with other sources)."""
    path = path or _REGISTRY_PATH
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    tenants = data.get("tenants") if isinstance(data, dict) else None
    return tenants if isinstance(tenants, list) else []


def _req_id_from_path(external_path: str) -> str | None:
    """Pull the Workday req id (e.g. R-12345 / JR0098765) out of externalPath,
    falling back to the path itself for dedupe."""
    if not external_path:
        return None
    m = re.search(r"([A-Za-z]{1,4}-?\d{4,})\b", external_path)
    return m.group(1) if m else external_path


def parse_postings(entry: dict, postings: list[dict]) -> list[dict]:
    """Turn a tenant's jobPostings array into unified Job dicts.

    Pure function (no I/O) so it is unit-testable against a captured response.
    """
    host = entry.get("host", "")
    site = entry.get("site", "")
    display = entry.get("display") or entry.get("tenant") or host
    locale = entry.get("locale") or LOCALE

    out: list[dict] = []
    for p in postings:
        external_path = (p.get("externalPath") or "").strip()
        title = (p.get("title") or "").strip()
        if not title:
            continue
        # Public posting URL: https://{host}/{locale}/{site}{externalPath}
        url = f"https://{host}/{locale}/{site}{external_path}" if external_path else f"https://{host}/{locale}/{site}"
        out.append({
            "source": "workday",
            "company": display,
            "title": title,
            "location": (p.get("locationsText") or "").strip(),
            "url": url,
            "apply_url": url,
            "posted_at": (p.get("postedOn") or None),  # relative string, e.g. "Posted 3 Days Ago"
            "raw_id": _req_id_from_path(external_path),
            "department": None,
            "description_excerpt": None,  # list endpoint carries no JD body; fetched later at scoring time
        })
    return out


def fetch_one(entry: dict, search_text: str = DEFAULT_SEARCH,
              timeout: int = 12, pause_seconds: float = 0.2) -> list[dict]:
    """Fetch (and paginate through) all matching jobs for one Workday tenant.

    Returns a list of unified Job dicts. Empty list on any failure — per-tenant
    failures are non-fatal so the caller continues with the next tenant.
    """
    if requests is None:
        return []
    host = entry.get("host")
    tenant = entry.get("tenant")
    site = entry.get("site")
    if not (host and tenant and site):
        return []

    endpoint = CXS_JOBS.format(host=host, tenant=tenant, site=site)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "dreamjob-agent/1.0",
    }

    aggregated: list[dict] = []
    offset = 0
    for _page in range(MAX_PAGES_PER_TENANT):
        body = {"appliedFacets": {}, "limit": PAGE_SIZE,
                "offset": offset, "searchText": search_text}
        try:
            resp = requests.post(endpoint, json=body, headers=headers, timeout=timeout)
        except Exception:
            break
        if resp.status_code != 200:
            break
        try:
            data = resp.json()
        except ValueError:
            break

        postings = data.get("jobPostings") or []
        if not postings:
            break
        aggregated.extend(parse_postings(entry, postings))

        total = data.get("total")
        offset += PAGE_SIZE
        if isinstance(total, int) and offset >= total:
            break
        time.sleep(pause_seconds)

    return aggregated


def fetch_all_jobs(registry: list[dict] | None = None,
                   search_text: str = DEFAULT_SEARCH,
                   pause_seconds: float = 0.3) -> list[dict]:
    """Fetch all matching jobs across every tenant in the registry.

    Loops `data/workday_tenants.json` by default. Per-tenant failures are
    swallowed (logged by the caller via counts), so one bad slug never blocks
    the rest.
    """
    registry = registry if registry is not None else load_registry()
    aggregated: list[dict] = []
    for entry in registry:
        aggregated.extend(fetch_one(entry, search_text=search_text))
        time.sleep(pause_seconds)
    return aggregated


def verify_tenants(registry: list[dict] | None = None) -> list[dict]:
    """Probe each tenant once and report whether the (host, tenant, site) triple
    resolves to live jobs. Use in production to lock in correct slugs:

        python agent/sources/workday.py --verify

    Returns a list of {display, ok, total_sampled, sample_title, error}.
    """
    registry = registry if registry is not None else load_registry()
    report: list[dict] = []
    for entry in registry:
        jobs = fetch_one(entry, search_text=DEFAULT_SEARCH)
        report.append({
            "display": entry.get("display"),
            "host": entry.get("host"),
            "site": entry.get("site"),
            "ok": bool(jobs),
            "sampled": len(jobs),
            "sample_title": jobs[0]["title"] if jobs else None,
        })
    return report


def main() -> int:
    if "--verify" in sys.argv:
        report = verify_tenants()
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        ok = sum(1 for r in report if r["ok"])
        print(f"# {ok}/{len(report)} Workday tenants verified live", file=sys.stderr)
        return 0
    jobs = fetch_all_jobs()
    json.dump(jobs, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"# {len(jobs)} jobs from {len(load_registry())} Workday tenants",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
