"""Multi-actor LinkedIn jobs pull — runs 4 top-rated Apify actors in parallel,
dedupes by canonical URL, applies the user's title include/exclude filter.

Per-user requirements (2026-06-16):
- Hit multiple top-rated actors so no single actor's gaps kill coverage
- Recently posted / open for applying (past 7 days)
- INCLUDE: Head of Product, Director (of) Product, Principal PM, Group PM (GPM),
  VP Product, Senior PM, Lead PM, Chief Product Officer, AI/GenAI PM
- EXCLUDE: anything with "Engineering" in the title (Product Engineering,
  Engineering Manager, Engineering Lead, etc.)
- India + Remote-from-India

Environment:
  APIFY_TOKEN — required (read from GitHub secret)

Outputs (committed by the workflow):
  data/jobs/2026-06-16_linkedin_multi_actor.jsonl       — all unique jobs
  data/jobs/2026-06-16_linkedin_multi_actor_summary.md  — human-readable summary
  data/jobs/raw/{actor-slug}_{query-slug}.json          — per-actor raw output
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOKEN = os.environ.get("APIFY_TOKEN", "").strip()

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OUT_DIR = Path("data/jobs")
RAW_DIR = OUT_DIR / "raw"

# ---- Title filter -----------------------------------------------------------
INCLUDE_PATTERNS = [
    r"\bhead\s+of\s+product\b",
    r"\b(director|sr\.?\s*director|senior\s+director|associate\s+director)\b.*\bproduct\b",
    r"\bproduct\b.*\b(director|head|owner|lead)\b",
    r"\b(principal|staff|lead|sr\.?|senior|group|gpm)\s+product\s+manager\b",
    r"\b(vp|vice\s+president|chief)\b.*\bproduct\b",
    r"\bprincipal\s+pm\b",
    r"\bstaff\s+pm\b",
    r"\b(ai|genai|llm|gen\s*ai|agentic)\s+product\s+manager\b",
    r"\bproduct\s+manager\b.*\b(ai|genai|llm|agentic|platform)\b",
    r"\bcpo\b",
    r"\bgpm\b",
]
EXCLUDE_PATTERNS = [
    r"\bengineering\b",   # user: "Product engineering is not a pass"
    r"\bengineer\b",
    r"\bdesign\b",
    r"\bdata\s+scientist\b",
    r"\bmarketing\s+manager\b",
    r"\bproject\s+manager\b",
    r"\bprogram\s+manager\b",
    r"\baccount\s+manager\b",
    r"\bsales\b",
    r"\binternship\b",
    r"\bintern\b",
]

LOCATION_INCLUDE = re.compile(
    r"india|bengaluru|bangalore|mumbai|hyderabad|delhi|gurgaon|gurugram|"
    r"noida|pune|chennai|^remote$|remote.*world|worldwide.*remote",
    re.IGNORECASE,
)


def title_passes(title: str) -> bool:
    t = (title or "").lower()
    if any(re.search(p, t, re.I) for p in EXCLUDE_PATTERNS):
        return False
    return any(re.search(p, t, re.I) for p in INCLUDE_PATTERNS)


# ---- Apify call helper ------------------------------------------------------

def call_actor(actor_id: str, payload: dict, timeout: int = 300):
    """POST to run-sync-get-dataset-items. Returns (items, error_str).

    On HTTP error, reads the response body — Apify 400s carry the exact
    validation message (e.g. "Field input.X is required"), which tells us
    the real schema. We surface that so a broken actor self-documents.
    """
    url = (f"https://api.apify.com/v2/acts/{actor_id}/"
           f"run-sync-get-dataset-items?token={TOKEN}")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        items = json.loads(data)
        return (items if isinstance(items, list) else [], "")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            err_body = ""
        return ([], f"HTTP {e.code}: {err_body}")
    except Exception as e:
        return ([], f"{type(e).__name__}: {e}")


def call_actor_multishape(actor_id: str, candidates: list[dict], timeout: int = 300):
    """Try each candidate payload; keep the first that returns >0 items.

    Returns (items, shape_index, last_error, account_block). `account_block`
    is True when the actor can't run at the ACCOUNT level (not rented /
    permissions not approved) — caller should skip it for all later queries
    rather than retry 6 shapes × every query.
    """
    last_err = ""
    for i, payload in enumerate(candidates):
        items, err = call_actor(actor_id, payload, timeout)
        if items:
            return items, i, "", False
        if err:
            last_err = err
            # Account-level blocks: no input shape will ever work — bail now.
            if ("actor-is-not-rented" in err or "not-approved" in err
                    or "permission" in err.lower() or "rent" in err.lower()):
                return [], -1, err, True
            sys.stderr.write(f"      shape#{i} err: {err[:160]}\n")
    return [], -1, last_err, False


# ---- Per-actor input builders -----------------------------------------------
# Each actor has its own input schema; we map a unified (keywords, location,
# limit, past_days) into the actor-specific shape.

def linkedin_search_url(keywords: str, location: str, past_days: int = 7) -> str:
    f_tpr_seconds = past_days * 86400
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": f"r{f_tpr_seconds}",
        "sortBy": "DD",  # date descending
    }
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def build_valig(kw, loc, limit, past_days):
    # KNOWN-GOOD (valig returned 719 in run #3). Single shape.
    return [{
        "title": kw, "location": loc, "limit": limit,
        "datePosted": f"r{past_days * 86400}",
        "experienceLevel": ["3", "4", "5"],  # Associate, Mid-Senior, Director
    }]


def build_curious_coder(kw, loc, limit, past_days):
    # KNOWN-GOOD (curious_coder returned 868 in run #3). Single shape.
    return [{
        "urls": [linkedin_search_url(kw, loc, past_days)],
        "count": limit,
        "scrapeCompany": False,
        "proxy": {"useApifyProxy": True},
    }]


def build_bebity(kw, loc, limit, past_days):
    # BROKEN so far (0 with searchUrl+rows and flat title/location). Try many
    # shapes; the run log captures each actor's validation error so we learn
    # the real schema even if all fail.
    su = linkedin_search_url(kw, loc, past_days)
    return [
        {"title": kw, "location": loc, "rows": limit, "publishedAt": f"r{past_days*86400}"},
        {"keyword": kw, "location": loc, "count": limit, "proxy": {"useApifyProxy": True}},
        {"urls": [su], "count": limit, "proxy": {"useApifyProxy": True}},
        {"startUrls": [{"url": su}], "maxItems": limit},
        {"queries": [kw], "locationName": loc, "maxItems": limit},
        {"searchUrl": su, "maxResults": limit},
    ]


def build_harvestapi(kw, loc, limit, past_days):
    # BROKEN so far (0 with includeKeyword/locationName/pagesToFetch). HarvestAPI
    # no-cookies actors vary; try the common shapes.
    su = linkedin_search_url(kw, loc, past_days)
    past_label = "Past week" if past_days <= 7 else "Past month"
    return [
        {"searchQuery": kw, "location": loc, "maxItems": limit},
        {"keywords": kw, "locationName": loc, "maxItems": limit, "publishedAt": past_label},
        {"title": kw, "location": loc, "maxItems": limit},
        {"query": kw, "location": loc, "maxItems": limit, "datePosted": past_label},
        {"searchUrls": [su], "maxItems": limit},
        {"includeKeyword": kw, "locationName": loc, "datePosted": past_label, "pagesToFetch": 5},
    ]


ACTORS = [
    # Apify API REQUIRES "~" not "/" in actor IDs — slash 404s
    ("valig",         "valig~linkedin-jobs-scraper",         build_valig),
    ("curiouscoder",  "curious_coder~linkedin-jobs-scraper", build_curious_coder),
    ("harvestapi",    "harvestapi~linkedin-job-search",      build_harvestapi),
    # bebity dropped: 'actor-is-not-rented' (paid rental); user opted out
    # 2026-06-16. Re-add ("bebity","bebity~linkedin-jobs-scraper",build_bebity)
    # if rented later.
]

# Optional actor subset (workflow input ACTORS="bebity,harvestapi" to isolate).
_actor_filter = {a.strip().lower() for a in os.environ.get("ACTORS", "").split(",") if a.strip()}
if _actor_filter:
    ACTORS = [a for a in ACTORS if a[0] in _actor_filter]

# ---- Query set — BROADENED, no company names ("any role that fits") --------
# 24 role×seniority×domain×location combos. Catches everything by title, not
# by company, per user 2026-06-16: "find any and every role that fits".
QUERIES = [
    ("Head of Product", "India"),
    ("Director of Product", "India"),
    ("Director Product Management", "Bengaluru, India"),
    ("Principal Product Manager", "India"),
    ("Principal Product Manager AI", "Bengaluru, India"),
    ("Group Product Manager", "India"),
    ("VP Product", "India"),
    ("Vice President Product", "Mumbai, India"),
    ("Senior Product Manager", "Bengaluru, India"),
    ("Senior Product Manager AI", "India"),
    ("Senior Product Manager Platform", "Hyderabad, India"),
    ("Lead Product Manager", "Bengaluru, India"),
    ("Staff Product Manager", "India"),
    ("Chief Product Officer", "India"),
    ("Product Director", "Gurgaon, India"),
    ("GenAI Product Manager", "India"),
    ("AI Product Manager", "Bengaluru, India"),
    ("Director Product AI", "India"),
    ("Head of Product AI", "Remote"),
    ("Principal Product Manager Payments", "India"),
    ("Director Product Fintech", "Mumbai, India"),
    ("Senior Product Manager Data", "Bengaluru, India"),
    ("Group Product Manager Growth", "India"),
    ("Product Lead", "India"),
]

# Coverage knobs (credits not a concern per user).
LIMIT_PER_QUERY = int(os.environ.get("LIMIT_PER_QUERY", "200"))
PAST_DAYS = int(os.environ.get("PAST_DAYS", "30"))
RUN_TAG = os.environ.get("RUN_TAG") or datetime.now(timezone.utc).strftime("%H%M")

# ---- Field normalizer (each actor returns different shapes) ----------------

def _txt(v) -> str:
    """Coerce any field value to a string. harvestapi nests company/location
    as objects like {"name": "Google", "url": ...} or {"text": ...}; valig and
    curious_coder return plain strings. Handles str / dict / list / None."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("name", "text", "title", "displayName", "label", "value"):
            if v.get(k):
                return _txt(v[k])
        return ""
    if isinstance(v, list):
        return ", ".join(_txt(x) for x in v if x)
    return str(v).strip()


def _first(item: dict, *keys) -> str:
    for k in keys:
        s = _txt(item.get(k))
        if s:
            return s
    return ""


def normalize(item: dict, actor_slug: str) -> dict | None:
    """Coerce one item from any actor into a common job dict.
    Returns None if essential fields missing.
    """
    title = _first(item, "title", "jobTitle", "position")
    company = _first(item, "company", "companyName", "organization", "companyInfo")
    location = _first(item, "location", "formattedLocation", "jobLocation")
    url = _first(item, "link", "url", "jobUrl", "applyUrl", "jobPostingUrl")
    posted = _first(item, "postedAt", "publishedAt", "listedAt", "postedDate", "datePosted")
    desc = (_first(item, "description", "descriptionText", "jobDescription"))[:1500]
    # Compensation — different actors expose it under different keys.
    # User explicitly asked to map by experience + compensation (2026-06-16).
    comp = (item.get("salary") or item.get("salaryRange")
             or item.get("compensation") or item.get("salaryInsights")
             or item.get("payRange") or "")
    if isinstance(comp, dict):
        # Normalise common dict shapes like {min, max, currency} or {text}
        comp = (comp.get("text") or comp.get("range")
                  or " - ".join(str(v) for v in [comp.get("min"), comp.get("max")] if v)
                  or json.dumps(comp))
    seniority_signal = (item.get("seniority") or item.get("seniorityLevel")
                          or item.get("experienceLevel") or "")
    employment_type = (item.get("employmentType") or item.get("jobType") or "")
    applicants = (item.get("applicants") or item.get("applicantsCount") or "")
    if not (title and url):
        return None
    # Canonicalize LinkedIn URL: strip query params, keep numeric job id
    m = re.search(r"linkedin\.com/jobs/view/(\d+)", url) \
        or re.search(r"currentJobId=(\d+)", url)
    canonical = (f"https://www.linkedin.com/jobs/view/{m.group(1)}"
                  if m else url.split("?")[0])
    return {
        "title": title, "company": company, "location": location,
        "url": canonical, "posted_at": str(posted),
        "compensation": str(comp) if comp else "",
        "seniority": str(seniority_signal) if seniority_signal else "",
        "employment_type": str(employment_type) if employment_type else "",
        "applicants": str(applicants) if applicants else "",
        "actor": actor_slug, "description_excerpt": desc,
    }


# ---- Main -------------------------------------------------------------------

def main() -> int:
    if not TOKEN:
        sys.stderr.write("APIFY_TOKEN env var missing — refusing to run\n")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"# Multi-actor LinkedIn pull — {TODAY}")
    print(f"  Token length: {len(TOKEN)}")
    print(f"  Actors: {[a[0] for a in ACTORS]}")
    print(f"  Queries: {len(QUERIES)}")
    print()

    print(f"  Actors active: {[a[0] for a in ACTORS]}")
    print(f"  limit/query={LIMIT_PER_QUERY}  past_days={PAST_DAYS}  run_tag={RUN_TAG}")
    print()

    all_jobs: dict[str, dict] = {}  # canonical_url -> job
    per_actor_stats: dict[str, dict] = {a[0]: {"raw": 0, "normalized": 0,
                                                  "shape": None, "last_err": ""}
                                          for a in ACTORS}
    dead_actors: set[str] = set()  # account-blocked (not rented / not approved)

    for kw, loc in QUERIES:
        q_slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{kw}_{loc}").strip("_").lower()
        print(f"=== Query: {kw!r} @ {loc!r} ===")
        for slug, actor_id, build in ACTORS:
            if slug in dead_actors:
                continue  # account-blocked earlier; don't waste calls
            candidates = build(kw, loc, LIMIT_PER_QUERY, PAST_DAYS)
            print(f"  [{slug:14}] calling {actor_id}…", end=" ", flush=True)
            t0 = time.time()
            items, shape_i, last_err, account_block = call_actor_multishape(
                actor_id, candidates, timeout=300)
            dt = time.time() - t0
            print(f"got {len(items)} items (shape#{shape_i}) in {dt:.1f}s"
                  + (f"  [err: {last_err[:80]}]" if (not items and last_err) else ""))
            if account_block:
                dead_actors.add(slug)
                per_actor_stats[slug]["last_err"] = last_err
                print(f"      → {slug} ACCOUNT-BLOCKED — skipping for the rest of the run")
            (RAW_DIR / f"{slug}_{q_slug}.json").write_text(
                json.dumps(items, indent=2, ensure_ascii=False))
            per_actor_stats[slug]["raw"] += len(items)
            if shape_i >= 0:
                per_actor_stats[slug]["shape"] = shape_i
            if last_err:
                per_actor_stats[slug]["last_err"] = last_err
            for it in items:
                n = normalize(it, slug)
                if not n:
                    continue
                per_actor_stats[slug]["normalized"] += 1
                if n["url"] not in all_jobs:
                    all_jobs[n["url"]] = n
        print()

    # Filter pass
    surviving = []
    drop_reasons = {"title_excluded": 0, "title_no_include": 0,
                     "location_outside_target": 0}
    for url, job in all_jobs.items():
        if not title_passes(job["title"]):
            t = job["title"].lower()
            if any(re.search(p, t, re.I) for p in EXCLUDE_PATTERNS):
                drop_reasons["title_excluded"] += 1
            else:
                drop_reasons["title_no_include"] += 1
            continue
        if not LOCATION_INCLUDE.search(job["location"]):
            drop_reasons["location_outside_target"] += 1
            continue
        surviving.append(job)

    # Sort by posted_at desc (fall back to no-op)
    surviving.sort(key=lambda j: j.get("posted_at", ""), reverse=True)

    # Write outputs — RUN_TAG suffix prevents clobbering earlier runs same day
    out_file = OUT_DIR / f"{TODAY}_{RUN_TAG}_linkedin_multi_actor.jsonl"
    with out_file.open("w") as f:
        for j in surviving:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    summary_file = OUT_DIR / f"{TODAY}_{RUN_TAG}_linkedin_multi_actor_summary.md"
    with summary_file.open("w") as f:
        f.write(f"# LinkedIn multi-actor pull — {TODAY}\n\n")
        f.write(f"**Token:** present ({len(TOKEN)} chars)\n")
        f.write(f"**Queries:** {len(QUERIES)}\n")
        f.write(f"**Actors:** {', '.join(a[0] for a in ACTORS)}\n\n")
        f.write("## Per-actor stats\n\n| Actor | Raw items | Normalised | Notes |\n|---|---|---|---|\n")
        for slug in per_actor_stats:
            s = per_actor_stats[slug]
            if s["raw"] > 0:
                note = f"OK (input shape #{s['shape']})"
            else:
                note = f"⚠ 0 — last err: {(s['last_err'] or 'n/a')[:120]}"
            f.write(f"| {slug} | {s['raw']} | {s['normalized']} | {note} |\n")
        f.write(f"\n## Dedupe + filter\n\n"
                  f"- Unique canonical URLs collected: **{len(all_jobs)}**\n"
                  f"- After title/location filter: **{len(surviving)}**\n"
                  f"- Dropped: {drop_reasons}\n\n"
                  f"## Final list ({len(surviving)} jobs)\n\n"
                  f"| Posted | Company | Title | Location | Comp | Seniority | Actor |\n"
                  f"|---|---|---|---|---|---|---|\n")
        for j in surviving:
            posted = (j.get("posted_at") or "")[:10]
            comp = (j.get("compensation") or "—")[:30]
            sen = (j.get("seniority") or "—")[:20]
            f.write(f"| {posted} | {j['company']} | [{j['title']}]({j['url']}) | "
                      f"{j['location']} | {comp} | {sen} | {j['actor']} |\n")

    print(f"\n=== SUMMARY ===")
    print(f"  All unique URLs across actors: {len(all_jobs)}")
    print(f"  After title/location filter:   {len(surviving)}")
    print(f"  Drops: {drop_reasons}")
    print(f"  Per-actor raw counts: {[(s, per_actor_stats[s]['raw']) for s,_,_ in ACTORS]}")
    print(f"\nWritten:")
    print(f"  {out_file}")
    print(f"  {summary_file}")
    print(f"  raw/  ({len(list(RAW_DIR.glob('*.json')))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
