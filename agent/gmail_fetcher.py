"""Gmail API fetcher — pulls LinkedIn job-alert threads and extracts job URLs.

Reads creds from env vars (same OAuth client as gmail_sender):
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN

Usage (programmatic):
    from agent.gmail_fetcher import fetch_linkedin_job_urls
    urls = fetch_linkedin_job_urls(days=3)
    # → ["https://www.linkedin.com/jobs/view/4409784554", ...]

CLI:
    python agent/gmail_fetcher.py --days 3 --out outputs/{date}/_gmail_linkedin_urls.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
GMAIL_THREAD_DETAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads/{tid}"

# LinkedIn job URL pattern — captures the numeric job ID
JOB_URL_RE = re.compile(
    r"https?://(?:www\.|in\.)?linkedin\.com/(?:comm/)?jobs/view/(\d{8,12})"
)


def _exchange_refresh_token() -> str:
    cid = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    cs = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    rt = os.environ.get("GMAIL_REFRESH_TOKEN", "").strip()
    if not all([cid, cs, rt]):
        raise RuntimeError("Gmail OAuth env vars missing")
    if requests is None:
        raise RuntimeError("requests not installed")
    resp = requests.post(GMAIL_TOKEN_URL, data={
        "client_id": cid, "client_secret": cs,
        "refresh_token": rt, "grant_type": "refresh_token",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _list_threads(access: str, query: str, max_results: int = 50) -> list[dict]:
    out = []
    page_token = None
    while True:
        params = {"q": query, "maxResults": min(50, max_results - len(out))}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(GMAIL_THREADS_URL,
                            headers={"Authorization": f"Bearer {access}"},
                            params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("threads", []))
        page_token = data.get("nextPageToken")
        if not page_token or len(out) >= max_results:
            break
    return out


def _get_thread_body(access: str, tid: str) -> str:
    r = requests.get(GMAIL_THREAD_DETAIL_URL.format(tid=tid),
                       headers={"Authorization": f"Bearer {access}"},
                       params={"format": "full"}, timeout=30)
    r.raise_for_status()
    body = ""
    for msg in r.json().get("messages", []):
        body += _walk_payload_for_text(msg.get("payload") or {}) + "\n"
    return body


def _walk_payload_for_text(payload: dict) -> str:
    """Recursively extract text/plain bodies from a Gmail message payload."""
    out = ""
    mt = payload.get("mimeType", "")
    if mt == "text/plain":
        data = (payload.get("body") or {}).get("data", "")
        if data:
            try:
                out += base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            except Exception:
                pass
    for part in payload.get("parts") or []:
        out += _walk_payload_for_text(part)
    return out


def _normalize_url(url: str) -> str:
    """Strip /comm/ prefix and tracking params; canonicalize to https://www.linkedin.com/jobs/view/{id}."""
    m = JOB_URL_RE.search(url)
    if not m:
        return ""
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}"


def fetch_linkedin_job_urls(days: int = 3, max_threads: int = 50) -> list[dict]:
    """Pull LinkedIn job-alert threads from the last N days and extract job URLs.

    Returns a list of dicts: [{"url": str, "thread_id": str, "thread_subject": str}, ...]
    URLs are deduped by job ID. Tracking params stripped.
    """
    access = _exchange_refresh_token()
    query = (
        f"(from:jobalerts-noreply@linkedin.com OR from:jobs-listings@linkedin.com "
        f"OR from:jobs-noreply@linkedin.com) newer_than:{days}d"
    )
    threads = _list_threads(access, query, max_results=max_threads)

    seen = {}
    for t in threads:
        tid = t["id"]
        try:
            body = _get_thread_body(access, tid)
        except Exception:
            continue
        # Try to grab the subject from the snippet (rough)
        subject = (t.get("snippet") or "")[:80]
        for m in JOB_URL_RE.finditer(body):
            job_id = m.group(1)
            if job_id in seen:
                continue
            seen[job_id] = {
                "url": f"https://www.linkedin.com/jobs/view/{job_id}",
                "thread_id": tid,
                "thread_subject": subject,
                "job_id": job_id,
            }
    return list(seen.values())


# ---------- Structured parsing of LinkedIn alert email bodies ----------
#
# LinkedIn alert bodies are deterministic plaintext. Each role looks like:
#
#     Director, Acceptance Solutions
#     Visa
#     Mumbai Metropolitan Region
#     [blank or hiring-badge]
#     View job: https://www.linkedin.com/comm/jobs/view/{id}/?...
#
# We extract title/company/location/url per role for the candidate pool.
# JD body is intentionally left blank — Step 2b (jd_enrich) fills it via
# the claude CLI's WebFetch tool. Honesty rule: we never fabricate JD text.

_BADGE_RE = re.compile(
    r"^(?:this company is actively hiring|fast growing|\d+\s+connections?|"
    r"actively hiring|easy apply|promoted|new|top applicant|"
    r"\d+\s+company\s+alumni|\d+\s+alumni|apply with resume.*profile)\b",
    re.IGNORECASE,
)


def parse_linkedin_alert_body(body: str) -> list[dict]:
    """Extract structured role records from a LinkedIn alert email body."""
    lines = [ln.strip() for ln in body.splitlines()]
    view_job_re = re.compile(
        r"View\s+job:\s*(https?://[^\s]*linkedin\.com/(?:comm/)?jobs/view/(\d{8,12})[^\s]*)",
        re.IGNORECASE,
    )
    results: dict[str, dict] = {}
    for i, line in enumerate(lines):
        m = view_job_re.search(line)
        if not m:
            continue
        job_id = m.group(2)
        if job_id in results:
            continue
        prior: list[str] = []
        j = i - 1
        while j >= 0 and len(prior) < 8:
            s = lines[j].strip()
            if s and not s.startswith("---") and not s.lower().startswith("view job"):
                prior.append(s)
            j -= 1
        prior.reverse()
        if prior and _BADGE_RE.match(prior[-1]):
            prior.pop()
        if len(prior) < 3:
            continue
        title, company, location = prior[-3], prior[-2], prior[-1]
        if len(title) > 200 or len(company) > 120 or len(location) > 120:
            continue
        if any(s.lower().startswith(("see all jobs", "edit alert", "manage your"))
               for s in (title, company, location)):
            continue
        results[job_id] = {
            "title": title,
            "company": company,
            "location": location,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "apply_url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "raw_id": job_id,
        }
    return list(results.values())


def fetch_linkedin_alert_jobs(days: int = 3, max_threads: int = 50) -> list[dict]:
    """Pull LinkedIn alert threads and return per-role dicts (title/company/...)."""
    access = _exchange_refresh_token()
    query = (
        f"(from:jobalerts-noreply@linkedin.com OR from:jobs-listings@linkedin.com "
        f"OR from:jobs-noreply@linkedin.com) newer_than:{days}d"
    )
    threads = _list_threads(access, query, max_results=max_threads)
    out: dict[str, dict] = {}
    for t in threads:
        tid = t["id"]
        try:
            body = _get_thread_body(access, tid)
        except Exception:
            continue
        for rec in parse_linkedin_alert_body(body):
            jid = rec["raw_id"]
            if jid in out:
                continue
            rec["source"] = "gmail_linkedin"
            rec["description_excerpt"] = ""
            rec["posted_at"] = None
            out[jid] = rec
    return list(out.values())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--max-threads", type=int, default=50)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    urls = fetch_linkedin_job_urls(days=args.days, max_threads=args.max_threads)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(urls, open(args.out, "w"), indent=2, ensure_ascii=False)
    print(f"[gmail_fetcher] {len(urls)} unique LinkedIn job URLs from last {args.days}d → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
