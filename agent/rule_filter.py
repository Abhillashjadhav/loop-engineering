"""Rule-based filter — cheap, deterministic, $0 in tokens.

Drops candidates that don't match basic profile constraints before any
LLM scoring runs. Typically removes 70–80% of raw results.

Dedupe window: jobs already seen in `outputs/seen_index.jsonl` within
the last 60 days are skipped silently (no-resurface rule).

Decline-list matching: case-insensitive substring match on the company
name field, so any sister entity listed in `decline_list_companies`
(e.g., "AWS", "Amazon Web Services", "Twitch", "CTL", "Vista",
"Vistaprint") triggers the block.

I/O is JSONL (one Job per line) on both ends so the pipeline stays
streamable. Drop stats are written alongside the output as
`_filter_summary.json` for audit.

Usage:
    python agent/rule_filter.py \
        --input outputs/{date}/_raw_candidates.jsonl \
        --profile profile/master_profile.json \
        --output outputs/{date}/_filtered_candidates.jsonl \
        --seen-index outputs/seen_index.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Title pattern — Director+/Principal+/Group/Head/VP (target band) OR
# Senior/Staff/Sr/Lead Product Manager (stretch band, tagged later).
# We accept the stretch band so the JD-aware scorer + resume tailor can decide,
# rather than the regex silently killing roles the user would consider.
#
# Bug fixed 2026-05-26: the prior version required the seniority anchor
# AND a separate (product|pm) token to appear after it. That broke
# "Senior Product Manager" / "Sr PM" / "Staff Product Manager" since
# the "product/pm" inside the seniority phrase is the only one — there
# is no second mention. The fix splits the alternation into two arms:
#   1. Bare-senior shapes: "(senior|sr|staff|lead) (product|pm)..."
#      with optional trailing focus area, no second product token needed.
#   2. Heavyweight shapes: "(director|principal|group|head of|vp|gpm)
#      ... (product|pm) ..." (the original logic).
TITLE_RE = re.compile(
    # Arm 1: bare-senior PM titles — "Senior Product Manager", "Sr PM",
    # "Staff Product Manager, Growth", "Lead PM", "Senior Lead Digital
    # Product Manager". Product/PM is the noun; seniority is the modifier.
    # Allow up to 3 words between seniority and product/pm to catch
    # "Senior Lead Digital Product" / "Staff Software Product" etc.
    # The word-bridge separator tolerates comma / dash / slash / ampersand so
    # punctuated titles survive — e.g. "Senior Manager, AI Product Management"
    # and "Senior Manager - GenAI Product" (Workday/LinkedIn format the band
    # this way). A product/pm token is still REQUIRED after the bridge, so
    # "Senior Manager, Sales" / "Senior Manager, Engineering" stay excluded.
    r"\b(senior|sr\.?|staff|senior\s+staff|lead)\s+(?:\w+[\s,/&-]+){0,3}(product\s+manager|pm|product)\b"
    r"|"
    # Arm 2: heavyweight titles — "Director of Product", "Principal PM",
    # "Group Product Manager", "Head of Product", "VP Product", "GPM".
    r"\b(director|principal|group|head\s+of|vp|vice\s+president|gpm)\b.*\b(product|pm)\b"
    r"|"
    # Arm 3: reverse order — "Product Director", "Product Lead, AI",
    # "Product VP", etc.
    r"\b(product|pm)\b.*\b(director|principal|head|vp|vice\s+president|gpm|lead)\b",
    re.IGNORECASE,
)

# Disqualifying titles — even if "Director" or "Senior PM" appears, drop these.
# "engineering manager" and "engineer" stay disqualifying; we are PM-only.
# NOTE: "operations" removed 2026-06-17 — it was a false positive that blocked
# "Director, Product Operations" at companies like Mastercard. Product Operations
# is a legitimate PM domain; the scorer should decide, not the regex.
DISQUALIFY_TITLE_RE = re.compile(
    r"\b(intern|associate\s+product|junior|jr\.?\s+product|engineer|engineering\s+manager|"
    r"data\s+scientist|designer|product\s+design|design\s+lead|"
    r"sales|marketing|customer\s+success|"
    r"hr|finance|legal|recruiter|recruiting)\b",
    re.IGNORECASE,
)

# Location matchers — accept all major Indian metros and tier-2 hubs.
# Pune/NCR/Chennai used to be partial-credit in scorer; they are now full-pass at filter.
PREFERRED_LOC_RE = re.compile(
    r"\b(remote|bengaluru|bangalore|mumbai|hyderabad|pune|chennai|"
    r"gurgaon|gurugram|noida|delhi|ncr|india)\b",
    re.IGNORECASE,
)

# Hard reject locations (anywhere outside India that isn't Remote)
NON_INDIA_LOC_RE = re.compile(
    r"\b(united states|usa|us\b|canada|uk|united kingdom|germany|"
    r"france|singapore|dublin|tokyo|sydney|berlin|amsterdam|"
    r"new york|san francisco|seattle|london|paris|toronto)\b",
    re.IGNORECASE,
)


def _job_hash(job: dict) -> str:
    """Stable hash for dedupe — based on company + normalized title + url."""
    s = f"{job.get('company','')}|{job.get('title','').strip().lower()}|{job.get('url','')}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# Cross-source preference. When the same (company, normalized_title,
# location) surfaces from multiple sources — e.g. an Indeed query and a
# parsed LinkedIn-Jobs digest — keep the highest-priority one. LinkedIn
# alerts usually carry richer JD context than Indeed snippets; Naukri /
# Hirist sit in between.
SOURCE_PRIORITY = {
    "linkedin_apify": 5,    # richest JD context, sourced via Apify residential proxy
    "indeed": 4,
    "gmail_linkedin": 4,    # quality-filtered by user's saved alert; same tier as Indeed
    "gmail_naukri": 3,
    "gmail_hirist": 2,
    # Legacy aliases retained for backwards compat with older
    # _raw_candidates.jsonl files written under the previous naming.
    "linkedin_alert": 4,
    "naukri_alert": 3,
    "hirist_alert": 2,
    "gmail": 1,
    "greenhouse": 1,
    "lever": 1,
    "ashby": 1,
}


def _intra_run_dedupe_key(job: dict) -> str:
    """Hash on (company, normalized_title, location) for in-batch dedupe.

    Multiple Indeed query variants and Gmail alert digests often hit the
    same role with different URLs and snippet lengths. URL is intentionally
    excluded so we collapse those variants. Used only for the in-batch
    dedupe — the cross-day `seen_index` keeps using `_job_hash` (which
    includes the URL).
    """
    company = (job.get("company") or "").strip().lower()
    title = (job.get("title") or "").strip().lower()
    location = (job.get("location") or "").strip().lower()
    s = f"{company}|{title}|{location}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _job_pref_score(job: dict) -> tuple[int, int]:
    """Return (source priority, description length). Higher = preferred."""
    src = (job.get("source") or "").lower()
    return (
        SOURCE_PRIORITY.get(src, 0),
        len(job.get("description_excerpt") or ""),
    )


def dedupe_jobs(jobs: list[dict]) -> tuple[list[dict], int]:
    """Drop duplicate (company, normalized_title, location) triples.

    Preference order on collision:
      1. Higher SOURCE_PRIORITY (linkedin_alert > naukri/hirist > indeed)
      2. Longer description_excerpt as tiebreaker

    Order-stable: the kept entry retains the first-seen position for its
    key; subsequent duplicates only replace it if they outscore it.

    Returns (deduped_list, dropped_count).
    """
    by_hash: dict[str, int] = {}  # key -> index into result list
    result: list[dict] = []
    for job in jobs:
        key = _intra_run_dedupe_key(job)
        if key not in by_hash:
            by_hash[key] = len(result)
            result.append(job)
            continue
        existing = result[by_hash[key]]
        if _job_pref_score(job) > _job_pref_score(existing):
            result[by_hash[key]] = job
    return result, len(jobs) - len(result)


def load_seen_index(path: Path, days: int = 60) -> set[str]:
    """Load hashes of jobs seen recently, using score-aware windows.

    Window logic (prevents the 60-day flat block from silently burying
    near-misses that can now score higher after adjacent-skill bumps):
      - score >= 80 (resume generated): full `days` window (default 60d)
      - 60 <= score < 80 (near-miss surfaced in brief): 7-day window
      - score < 60 (dropped silently): 1-day window (only prevents same-day dupes)
      - score missing / unknown: falls back to full `days` window (safe default)
    """
    if not path.exists():
        return set()
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    with path.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat(rec.get("seen_at", ""))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            score = rec.get("score")
            if score is None:
                window = days
            elif score >= 80:
                window = days          # full block: resume was generated, user is aware
            elif score >= 60:
                window = 7             # near-miss: re-surface weekly (scoring can change)
            else:
                window = 1             # dropped silently: only block same-day dupes
            cutoff = now - timedelta(days=window)
            if ts >= cutoff:
                seen.add(rec["hash"])
    return seen


def passes_filter(job: dict, decline_list: list[str], seen: set[str]) -> tuple[bool, str]:
    """Check if a job passes all rule filters.

    Returns (passed, reason_if_dropped).
    """
    title = job.get("title", "")
    location = job.get("location", "")
    company = job.get("company", "")

    # Title check
    if not TITLE_RE.search(title):
        return False, "title_no_match"
    if DISQUALIFY_TITLE_RE.search(title):
        return False, "title_disqualifying"

    # Location check (must be India/Remote — explicit non-India = drop)
    if location and NON_INDIA_LOC_RE.search(location):
        # Check if "remote" is also in there — some roles say "Remote (US)"
        # which we still drop because it's not India-eligible
        if not re.search(r"\bremote.*india\b|\bindia.*remote\b", location, re.I):
            return False, f"location_outside_india ({location})"
    if location and not PREFERRED_LOC_RE.search(location):
        # No India / Remote signal at all — drop unless empty (which we tolerate)
        return False, f"location_not_preferred ({location})"

    # Decline list check — case-insensitive substring match on the
    # company name field. The decline list (loaded from
    # profile/master_profile.json -> decline_list_companies) is expected
    # to enumerate sister entities (e.g., "Amazon", "AWS", "Twitch",
    # "Cimpress", "CTL", "Vista", "Vistaprint"); matching as a substring
    # ensures variants like "Amazon Web Services" or "VistaCreate" are
    # blocked too.
    company_lower = company.lower()
    for declined in decline_list:
        if declined.lower() in company_lower:
            return False, f"decline_list ({declined})"

    # Already-seen check
    h = _job_hash(job)
    if h in seen:
        return False, "already_seen_recently"

    return True, "passed"


def filter_jobs(raw_path: Path, profile_path: Path,
                seen_index_path: Path) -> dict:
    """Apply all filters and return the filtered set with stats.

    Reads `raw_path` as JSONL (one Job per line) — the format emitted by
    `agent/sources/parse_responses.py` and the Gmail-label parsers in
    Step 1e. Blank lines are tolerated.

    Pipeline: load -> in-batch cross-source dedupe (collapse the same
    role from Indeed + LinkedIn/Naukri/Hirist; keep the highest-
    SOURCE_PRIORITY entry, longest description as tiebreaker) ->
    per-job rule filters (title, location, decline list, no-resurface).
    """
    with raw_path.open() as f:
        raw_jobs = [json.loads(line) for line in f if line.strip()]

    with profile_path.open() as f:
        profile = json.load(f)

    decline_list = profile.get("decline_list_companies", [])
    seen = load_seen_index(seen_index_path)

    deduped_jobs, dedupe_dropped = dedupe_jobs(raw_jobs)

    survivors: list[dict] = []
    drops_by_reason: dict[str, int] = {}

    for job in deduped_jobs:
        ok, reason = passes_filter(job, decline_list, seen)
        if ok:
            survivors.append(job)
        else:
            drops_by_reason[reason] = drops_by_reason.get(reason, 0) + 1

    return {
        "input_count": len(raw_jobs),
        "dedupe_dropped": dedupe_dropped,
        "after_dedupe_count": len(deduped_jobs),
        "output_count": len(survivors),
        "drop_rate": round(1 - len(survivors) / max(len(raw_jobs), 1), 3),
        "drops_by_reason": dict(sorted(drops_by_reason.items(),
                                       key=lambda kv: -kv[1])),
        "survivors": survivors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--profile", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--seen-index", type=Path,
                    default=Path("outputs/seen_index.jsonl"))
    args = ap.parse_args()

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 1

    result = filter_jobs(args.input, args.profile, args.seen_index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        for job in result["survivors"]:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")

    summary_path = args.output.parent / "_filter_summary.json"
    summary_path.write_text(json.dumps({
        "input_count": result["input_count"],
        "dedupe_dropped": result["dedupe_dropped"],
        "after_dedupe_count": result["after_dedupe_count"],
        "output_count": result["output_count"],
        "drop_rate": result["drop_rate"],
        "drops_by_reason": result["drops_by_reason"],
        "input_path": str(args.input),
        "output_path": str(args.output),
    }, indent=2, ensure_ascii=False))

    print(f"Filter: {result['input_count']} → "
          f"dedupe(-{result['dedupe_dropped']}) → "
          f"{result['after_dedupe_count']} → "
          f"{result['output_count']} survivors "
          f"(drop rate {result['drop_rate']*100:.1f}%)")
    for reason, count in result["drops_by_reason"].items():
        print(f"  - {reason}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
