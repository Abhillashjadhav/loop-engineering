"""Live HTTP fetcher for Greenhouse public job boards.

The existing greenhouse.py module is I/O-free by design (it was written
when the Routine sandbox blocked third-party API egress). This module
adds the network layer needed when running from environments with full
internet access — GitHub Actions runners, local dev, etc.

Greenhouse exposes a public, no-auth, no-rate-limit API:
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

Returns full JD + apply URL + location + department for every open role
at that company. Free.

Usage (programmatic):
    from agent.sources.greenhouse_fetch import fetch_all_jobs
    jobs = fetch_all_jobs()

CLI:
    python agent/sources/greenhouse_fetch.py > /tmp/gh_jobs.jsonl
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


GH_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

# Curated list of companies known to use Greenhouse AND post India PM roles
# (verified via spot-checks on their /jobs endpoints; some US-only companies
# excluded). Tuple is (slug, display_name).
GREENHOUSE_COMPANIES: list[tuple[str, str]] = [
    # Tier-1 tech with India offices
    ("stripe", "Stripe"),
    ("airbnb", "Airbnb"),
    ("coinbase", "Coinbase"),
    ("pinterest", "Pinterest"),
    ("dropbox", "Dropbox"),
    ("notion", "Notion"),
    ("figma", "Figma"),
    ("anthropic", "Anthropic"),
    ("discord", "Discord"),
    ("doordash", "DoorDash"),
    ("asana", "Asana"),
    ("datadog", "Datadog"),
    ("confluent", "Confluent"),
    ("hashicorp", "HashiCorp"),
    ("cloudflare", "Cloudflare"),
    ("plaid", "Plaid"),
    ("mongodb", "MongoDB"),
    ("snowflakecomputing", "Snowflake"),
    ("databricks", "Databricks"),
    ("gitlab", "GitLab"),
    ("twilio", "Twilio"),
    ("vercel", "Vercel"),
    ("ramp", "Ramp"),
    ("brex", "Brex"),
    # India-native using Greenhouse
    ("razorpay", "Razorpay"),
    ("postman", "Postman"),
    ("hasura", "Hasura"),
    ("atlan", "Atlan"),
    ("browserstack", "BrowserStack"),
    ("cred", "CRED"),
]


def _html_to_text(html: str) -> str:
    """Strip HTML tags from Greenhouse JD body. Best-effort, no external deps."""
    if not html:
        return ""
    # Drop scripts and styles first
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_one(slug: str, display_name: str, timeout: int = 30) -> list[dict]:
    """Fetch all open jobs for a single Greenhouse company.

    Returns a list of unified Job dicts. Empty list on any failure
    (network, HTTP 404 for unknown slug, malformed JSON, etc.) — per-company
    failures are non-fatal so caller can continue.
    """
    if requests is None:
        return []
    url = GH_API.format(slug=slug)
    try:
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "dreamjob-agent/1.0"})
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    out: list[dict] = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        depts = j.get("departments") or []
        dept = depts[0].get("name") if depts and isinstance(depts[0], dict) else None
        description = _html_to_text(j.get("content") or "")
        out.append({
            "source": "greenhouse",
            "company": display_name,
            "title": (j.get("title") or "").strip(),
            "location": loc.strip(),
            "url": (j.get("absolute_url") or "").strip(),
            "apply_url": (j.get("absolute_url") or "").strip(),
            "posted_at": j.get("updated_at"),
            "raw_id": str(j.get("id")) if j.get("id") is not None else None,
            "department": dept,
            "description_excerpt": description[:3000] if description else None,
        })
    return out


def fetch_all_jobs(companies: list[tuple[str, str]] | None = None,
                   pause_seconds: float = 0.2) -> list[dict]:
    """Fetch all open jobs across the configured Greenhouse company list.

    Returns a flat list of Job dicts. Loops through `GREENHOUSE_COMPANIES`
    by default. A small pause between requests keeps us courteous to the
    free API.
    """
    companies = companies if companies is not None else GREENHOUSE_COMPANIES
    aggregated: list[dict] = []
    for slug, display in companies:
        jobs = fetch_one(slug, display)
        aggregated.extend(jobs)
        time.sleep(pause_seconds)
    return aggregated


def main() -> int:
    jobs = fetch_all_jobs()
    json.dump(jobs, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"# {len(jobs)} jobs from {len(GREENHOUSE_COMPANIES)} "
          f"Greenhouse companies", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
