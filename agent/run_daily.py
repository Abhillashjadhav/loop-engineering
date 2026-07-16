"""Top-level daily orchestrator — wires fetch → filter → score → resume → notify.

Designed to run autonomously in GitHub Actions (or locally). All side-effecting
steps are wrapped in try/except so a single failure (e.g. Drive auth) doesn't
block the durable git-push channel.

Usage:
    python agent/run_daily.py --date 2026-05-11
    python agent/run_daily.py  # defaults to today UTC

Env vars (read via individual helpers):
    APIFY_TOKEN                       (agent/sources/apify_linkedin.py)
    ANTHROPIC_API_KEY                 (agent/scorer.py — optional)
    GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/TO  (agent/gmail_sender.py)
    GDRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN/PARENT_FOLDER_ID  (agent/drive_uploader.py)
    SKIP_APIFY=true                   (skip Apify; Greenhouse + uploaded datasets still run)
    SKIP_GREENHOUSE=true              (skip the free Greenhouse public API call)
    SKIP_WORKDAY=true                 (skip the free Workday public CXS API call)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resume generation: parallel workers. Claude CLI has per-process rate limits;
# 4 concurrent processes is safe and typically yields a 4x speedup over serial.
RESUME_MAX_WORKERS: int = int(os.environ.get("RESUME_MAX_WORKERS", "4"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import scorer  # noqa: E402
from agent import resume_pipeline as rp  # noqa: E402
from agent import invariants  # noqa: E402
from agent import llm_resume_generator  # noqa: E402

# Optional helpers — imported defensively because OAuth secrets may be absent locally
try:
    from agent import gmail_sender
except Exception:
    gmail_sender = None  # type: ignore[assignment]
try:
    from agent import drive_uploader
except Exception:
    drive_uploader = None  # type: ignore[assignment]
try:
    from agent import gmail_fetcher
except Exception:
    gmail_fetcher = None  # type: ignore[assignment]


def _log_step(date_dir: Path, payload: dict) -> None:
    """Append a single trajectory line — never raises."""
    try:
        date_dir.mkdir(parents=True, exist_ok=True)
        with (date_dir / "trajectory.jsonl").open("a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **payload},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass


def _is_test_mode() -> bool:
    """True when the run was dispatched with test mode (no-Apify) enabled."""
    return os.environ.get("TEST_MODE_NO_APIFY", "").lower() in ("1", "true", "yes")


def _count_source_rows(date_dir: Path, source: str) -> int:
    """Count rows in _raw_candidates.jsonl whose `source` field matches.

    Used by apify_fallback_mode=strict to verify Apify actually contributed.
    """
    path = date_dir / "_raw_candidates.jsonl"
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if json.loads(line).get("source") == source:
                n += 1
        except json.JSONDecodeError:
            continue
    return n


def _write_run_refused(date_dir: Path, reason: str) -> None:
    """Write RUN_REFUSED.md — the run was deliberately not executed.

    Distinct from RUN_FAILED.md (a stage produced bad output) and
    RUN_ANOMALY.md (output collapsed vs baseline): RUN_REFUSED means the
    orchestrator declined to run at all because the configuration was
    self-contradictory — e.g. test mode on while real Gmail signal exists.
    """
    date_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "# RUN REFUSED — orchestrator declined to execute\n\n"
        f"- **Timestamp (UTC):** {datetime.now(timezone.utc).isoformat()}\n"
        f"- **Reason:** {reason}\n\n"
        "Test mode (`test_mode_no_apify_zero_output_expected`) skips Apify and\n"
        "is EXPECTED to produce zero real output. It exists only to exercise\n"
        "the harness. When real Gmail job signal is present, a test-mode run\n"
        "would discard genuine candidates — so the orchestrator refuses.\n\n"
        "## What to do\n\n"
        "- For a real daily run: re-dispatch with test mode OFF.\n"
        "- To genuinely test the harness: do so on a date with no Gmail\n"
        "  alert signal, or accept that this refusal is the harness working.\n"
    )
    (date_dir / "RUN_REFUSED.md").write_text(content)


# ---------- 1a. Pull LinkedIn job URLs from Gmail alerts ----------

def fetch_gmail_alert_urls(date_dir: Path, days: int = 3) -> list[str]:
    if gmail_fetcher is None or not os.environ.get("GMAIL_REFRESH_TOKEN"):
        _log_step(date_dir, {"step": "1e-gmail", "decision": "skipped-no-token"})
        return []
    try:
        records = gmail_fetcher.fetch_linkedin_job_urls(days=days)
        urls = [r["url"] for r in records]
        json.dump(records, open(date_dir / "_gmail_linkedin_urls.json", "w"),
                    indent=2, ensure_ascii=False)
        _log_step(date_dir, {"step": "1e-gmail", "urls": len(urls), "days": days})
        return urls
    except Exception as e:
        _log_step(date_dir, {"step": "1e-gmail", "error": str(e), "decision": "continue-empty"})
        return []


# ---------- 1b. Fetch from all sources and aggregate ----------

def fetch_sources(date: str, date_dir: Path, gmail_urls: list[str]) -> int:
    """Aggregate raw candidates from all enabled sources.

    Sources called in order:
      1. Apify LinkedIn (query-based mode only — URL-mode disabled because
         valig actor doesn't support it). 5 queries × ~50 results = ~250 rows
         at ~\$0.10/day, well under \$5/month free credit.
      2. Greenhouse public API (FREE, no auth) — 30 curated companies known
         to use Greenhouse AND post India PM roles (Stripe, Airbnb, Coinbase,
         Pinterest, Confluent, Datadog, MongoDB, Snowflake, Databricks, GitLab,
         Razorpay, Postman, Atlan, Hasura, BrowserStack, CRED, etc.).
      3. Any pre-uploaded dataset_*.json files at the repo root (manual
         fallback for days when both sources fail).

    SKIP_APIFY=true skips source 1.
    SKIP_GREENHOUSE=true skips source 2.
    SKIP_WORKDAY=true skips source 2b.
    """
    skip_apify = os.environ.get("SKIP_APIFY", "").lower() in ("1", "true", "yes")
    skip_gh = os.environ.get("SKIP_GREENHOUSE", "").lower() in ("1", "true", "yes")
    skip_wd = os.environ.get("SKIP_WORKDAY", "").lower() in ("1", "true", "yes")
    sys.path.insert(0, str(ROOT / "agent" / "sources"))
    rows: dict[str, dict] = {}

    # Source 0: Gmail LinkedIn alerts (FREE, pre-filtered by user's saved search
    # preferences — typically the highest-quality source). Parses each alert
    # email body into structured {title, company, location, url} rows via
    # agent/gmail_fetcher.py:fetch_linkedin_alert_jobs. JD body is empty here;
    # the jd_enrich step (2b) fills it later via WebFetch.
    if gmail_fetcher is not None and os.environ.get("GMAIL_REFRESH_TOKEN"):
        try:
            alert_jobs = gmail_fetcher.fetch_linkedin_alert_jobs(days=3, max_threads=50)
            for j in alert_jobs:
                u = j.get("url") or ""
                if u and u not in rows:
                    rows[u] = j
            _log_step(date_dir, {"step": "1f-gmail-alerts",
                                   "rows": len(alert_jobs),
                                   "decision": "merged"})
        except Exception as e:
            _log_step(date_dir, {"step": "1f-gmail-alerts", "error": str(e),
                                   "decision": "continue-with-other-sources"})
    else:
        _log_step(date_dir, {"step": "1f-gmail-alerts",
                               "decision": "skipped-no-gmail-token"})

    # Source 1: Apify LinkedIn (paid, ~\$3/month)
    if not skip_apify:
        try:
            import apify_linkedin  # type: ignore[import-not-found]
            jobs = apify_linkedin.run_all_queries()
            for j in jobs:
                u = j.get("url") or ""
                if u and u not in rows:
                    rows[u] = j
            _log_step(date_dir, {"step": "1g-apify-queries", "rows": len(jobs)})
        except Exception as e:
            _log_step(date_dir, {"step": "1g-apify", "error": str(e),
                                   "decision": "continue-with-other-sources"})
    else:
        _log_step(date_dir, {"step": "1g-apify", "decision": "skipped-via-SKIP_APIFY-env"})

    # Source 2: Greenhouse public API (FREE)
    if not skip_gh:
        try:
            import greenhouse_fetch  # type: ignore[import-not-found]
            gh_jobs = greenhouse_fetch.fetch_all_jobs()
            for j in gh_jobs:
                u = j.get("url") or ""
                if u and u not in rows:
                    rows[u] = j
            _log_step(date_dir, {"step": "1h-greenhouse",
                                  "rows": len(gh_jobs),
                                  "companies": len(greenhouse_fetch.GREENHOUSE_COMPANIES)})
        except Exception as e:
            _log_step(date_dir, {"step": "1h-greenhouse", "error": str(e),
                                   "decision": "continue-with-other-sources"})
    else:
        _log_step(date_dir, {"step": "1h-greenhouse", "decision": "skipped-via-SKIP_GREENHOUSE-env"})

    # Source 2b: Workday public CXS API (FREE) — unlocks big-enterprise tenants
    # (Boeing, NVIDIA, Salesforce, ...) that don't use Greenhouse/Lever/Ashby.
    # Registry lives in data/workday_tenants.json so the discovery probe can
    # grow it without a code change. Per-tenant failures are non-fatal.
    if not skip_wd:
        try:
            import workday  # type: ignore[import-not-found]
            wd_jobs = workday.fetch_all_jobs()
            for j in wd_jobs:
                u = j.get("url") or ""
                if u and u not in rows:
                    rows[u] = j
            _log_step(date_dir, {"step": "1h2-workday",
                                  "rows": len(wd_jobs),
                                  "tenants": len(workday.load_registry())})
        except Exception as e:
            _log_step(date_dir, {"step": "1h2-workday", "error": str(e),
                                   "decision": "continue-with-other-sources"})
    else:
        _log_step(date_dir, {"step": "1h2-workday", "decision": "skipped-via-SKIP_WORKDAY-env"})

    # Source 3: any pre-uploaded dataset_*.{json,txt} files at repo root
    for pat in (f"dataset_linkedin-jobs-scraper_{date}_*.json",
                f"dataset_linkedin-jobs-scraper_{date}_*.txt"):
        for f in sorted((ROOT).glob(pat)):
            try:
                data = json.load(open(f))
            except Exception:
                continue
            for r in data:
                u = r.get("url")
                if u and u not in rows:
                    rows[u] = r

    # Source 4: multi-actor LinkedIn pull from data/jobs/ — the broad 24-query
    # pull (scripts/linkedin_multi_actor_pull.py) saves deduplicated results here.
    # Read the most recent file within the last 3 days so a pull from yesterday
    # still feeds today's daily run (avoids needing a fresh pull every single day).
    from datetime import date as _date, timedelta
    _today = _date.fromisoformat(date)
    _jobs_dir = ROOT / "data" / "jobs"
    _multi_actor_loaded = 0
    if _jobs_dir.exists():
        for _delta in range(3):
            _candidate_date = (_today - timedelta(days=_delta)).isoformat()
            _multi_path = _jobs_dir / f"{_candidate_date}_linkedin_multi_actor.jsonl"
            if _multi_path.exists():
                try:
                    with _multi_path.open() as _mf:
                        for _line in _mf:
                            _line = _line.strip()
                            if not _line:
                                continue
                            _r = json.loads(_line)
                            _u = _r.get("url", "")
                            if _u and _u not in rows:
                                _r.setdefault("source", "linkedin_multi_actor")
                                rows[_u] = _r
                                _multi_actor_loaded += 1
                    _log_step(date_dir, {
                        "step": "1i-multi-actor-jobs",
                        "file": str(_multi_path),
                        "new_rows": _multi_actor_loaded,
                        "decision": "merged",
                    })
                    break
                except Exception as _e:
                    _log_step(date_dir, {
                        "step": "1i-multi-actor-jobs",
                        "file": str(_multi_path),
                        "error": str(_e),
                        "decision": "skip",
                    })
                    break
        else:
            _log_step(date_dir, {
                "step": "1i-multi-actor-jobs",
                "decision": "no-file-found-within-3-days",
            })

    out = date_dir / "_raw_candidates.jsonl"
    with out.open("w") as fout:
        for r in rows.values():
            src = r.get("source", "linkedin_apify")
            rec = {
                "source": src,
                "company": r.get("companyName") or r.get("company") or "?",
                "title": r.get("title", "?"),
                "location": r.get("location") or "India",
                "url": r.get("url", ""),
                "apply_url": r.get("apply_url") or r.get("applyUrl") or r.get("url", ""),
                "posted_at": r.get("posted_at") or r.get("postedDate") or r.get("postedAt"),
                "raw_id": r.get("raw_id") or (str(r.get("id")) if r.get("id") else None),
                "department": r.get("department") or r.get("workType"),
                "description_excerpt": (r.get("description_excerpt")
                                         or r.get("description")
                                         or r.get("descriptionText") or "")[:3000],
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    from collections import Counter
    by_source = Counter(r.get("source", "linkedin_apify") for r in rows.values())
    _log_step(date_dir, {"step": "1-aggregate", "rows": len(rows),
                           "by_source": dict(by_source), "out": str(out)})
    return len(rows)


# Backwards-compat shim — old workflow YAML may still reference fetch_apify name
def fetch_apify(date: str, date_dir: Path, gmail_urls: list[str]) -> int:
    return fetch_sources(date, date_dir, gmail_urls)


# ---------- 2. Rule filter ----------

def run_rule_filter(date_dir: Path) -> int:
    """Invoke agent/rule_filter.py via subprocess so its existing CLI contract is honored."""
    inp = date_dir / "_raw_candidates.jsonl"
    out = date_dir / "_filtered_candidates.jsonl"
    profile = ROOT / "profile" / "master_profile.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "agent" / "rule_filter.py"),
         "--input", str(inp), "--profile", str(profile), "--output", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        _log_step(date_dir, {"step": "2-rule-filter", "error": proc.stderr[:500]})
        return 0
    n = sum(1 for _ in open(out))
    _log_step(date_dir, {"step": "2-rule-filter", "survivors": n, "stdout": proc.stdout.strip()[:300]})
    return n


# ---------- 2b. JD enrichment (fetch real JD body for Gmail-sourced roles) ----------

def enrich_jds(date_dir: Path) -> int:
    """Fill in missing JD bodies via the `claude` CLI's WebFetch.

    Reads `_filtered_candidates.jsonl`, rewrites it with `description_excerpt`
    populated for any candidate that arrived without one (typical of Gmail
    alert-sourced rows). Every candidate ends up with an explicit `jd_source`
    field — "actual" or "title_only" — so the scorer + brief can be transparent.
    """
    inp = date_dir / "_filtered_candidates.jsonl"
    if not inp.exists():
        return 0
    candidates = [json.loads(l) for l in open(inp) if l.strip()]
    react = lambda payload: _log_step(date_dir, payload)  # noqa: E731
    from agent import jd_enrich
    enriched = jd_enrich.enrich_candidates(candidates, react_logger=react)
    with inp.open("w") as f:
        for c in enriched:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    from collections import Counter
    by_source = Counter(c.get("jd_source", "unknown") for c in enriched)
    _log_step(date_dir, {"step": "2b-jd-enrich-summary",
                           "by_source": dict(by_source),
                           "decision": "complete"})
    return sum(1 for c in enriched if c.get("jd_source") == "actual")


# ---------- 3. Score (ReAct: per-role think → act → observe → log) ----------

def score(date_dir: Path) -> list[dict]:
    inp = date_dir / "_filtered_candidates.jsonl"
    profile = json.load(open(ROOT / "profile" / "master_profile.json"))
    candidates = [json.loads(l) for l in open(inp)]
    # ReAct logger: scorer emits one trajectory line per per-role decision.
    react = lambda payload: _log_step(date_dir, payload)  # noqa: E731
    # P4 — span-level tracer; each Claude CLI call gets prompt/completion/
    # latency/tokens captured to traces.jsonl for replay/audit.
    from agent.tracing import Tracer
    tracer = Tracer(date_dir)
    # COMMIT 4 — Gmail-only fallback. When apify_fallback_mode=gmail_only,
    # Apify was skipped; route scoring through the standalone
    # gmail_only_scorer (reduced-confidence, lowered fit threshold). This
    # does NOT touch scorer.py — it post-processes scorer.heuristic_score.
    if os.environ.get("APIFY_FALLBACK_MODE", "strict").lower() == "gmail_only":
        from agent import gmail_only_scorer
        scored = gmail_only_scorer.score_gmail_only(candidates, profile)
        _log_step(date_dir, {"step": "3-score",
                               "intent": "gmail_only fallback scoring",
                               "decision": "reduced-confidence",
                               "fit_threshold": gmail_only_scorer.GMAIL_ONLY_FIT_THRESHOLD})
    else:
        scored = scorer.score_candidates(candidates, profile,
                                           react_logger=react, tracer=tracer)
    json.dump(scored, open(date_dir / "_scored_candidates.json", "w"),
                indent=2, ensure_ascii=False)
    from collections import Counter
    disp = Counter(c["disposition"] for c in scored)
    methods = Counter(c.get("scored_via", "?") for c in scored)
    jd_sources = Counter(c.get("jd_source", "?") for c in scored)
    _log_step(date_dir, {"step": "3-score-summary",
                           "dispositions": dict(disp),
                           "scoring_methods": dict(methods),
                           "jd_sources": dict(jd_sources),
                           "decision": "complete"})
    return scored


# ---------- 4. Resume generation ----------

def _generate_one_resume(
    c: dict, date: str, date_dir: Path, profile: dict,
    out_dir: Path, decline_list: list,
) -> "Path | None":
    """Thread worker: generate a single resume PDF. Returns path or None."""
    from agent import jd_selection as _jsel
    company = re.sub(r"[^A-Za-z0-9]+", "_", c["company"]).strip("_") or "Unknown"
    title_slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")
    fname = f"{date}_{company}_{title_slug}.pdf"
    jd_id = f"{date}_{company}_{title_slug}"
    path = out_dir / fname

    matched = _jsel.declined_match(c["company"], decline_list)
    if matched:
        sidecar = _jsel.write_declined_sidecar(
            out_dir, jd_id, c["company"], matched, c.get("title", ""))
        _log_step(date_dir, {"step": "5d-declined", "company": c["company"],
                               "matched": matched, "artifact": sidecar.name,
                               "decision": "refuse-resume"})
        return None

    jd_text = c.get("description_excerpt", "") or c.get("description", "")
    try:
        used_llm = False
        if llm_resume_generator.llm_available() and len(jd_text.strip()) > 200:
            react = lambda payload: _log_step(date_dir, payload)  # noqa: E731
            result = llm_resume_generator.iterate(profile, jd_text, logger=react)
            if result.get("available") and result.get("draft"):
                rp.build_pdf_from_draft(path, result["draft"], profile, c)
                if path.exists():
                    used_llm = True
                    ledger = llm_resume_generator.write_ledger(path, result, c)
                    _log_step(date_dir, {"step": "5-llm-resume",
                                           "company": c["company"],
                                           "fitment": result.get("fitment"),
                                           "rounds": len(result.get("rounds", [])),
                                           "fab_counts": result.get("counts", {}),
                                           "stop_reason": result.get("stop_reason"),
                                           "ledger": ledger.name})
        if not used_llm:
            rp.build_pdf(path, c, profile)
            _log_step(date_dir, {"step": "5-resumes", "company": c["company"],
                                   "decision": "deterministic-renderer"})
        return path if path.exists() else None
    except Exception as e:
        _log_step(date_dir, {"step": "5-resumes", "company": c["company"], "error": str(e)})
        return None


def generate_resumes(scored: list[dict], date: str, date_dir: Path) -> list[Path]:
    fits = [c for c in scored if c["disposition"] in ("fit", "bumped_fit")]
    if not fits:
        _log_step(date_dir, {"step": "5-resumes", "decision": "no-fits-no-resumes"})
        return []

    # Font setup must happen in the main thread before workers start.
    rp.BASE_FONT = "Helvetica"
    rp.BOLD_FONT = "Helvetica-Bold"
    rp.ITALIC_FONT = "Helvetica-Oblique"
    rp.BOLD_ITALIC_FONT = "Helvetica-BoldOblique"
    rp.SERIF_FONT = "Times-Roman"
    rp._register_fonts = lambda: None  # noqa: E731
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Helvetica", normal="Helvetica", bold="Helvetica-Bold",
                        italic="Helvetica-Oblique", boldItalic="Helvetica-BoldOblique")
    for k in ("BASE_FONT", "BOLD_FONT", "ITALIC_FONT", "BOLD_ITALIC_FONT", "SERIF_FONT"):
        rp.build_styles.__globals__[k] = getattr(rp, k)

    profile = json.load(open(ROOT / "profile" / "master_profile.json"))
    profile = rp.patch_profile_for_skill_md(profile)

    out_dir = date_dir / "resumes_compact"
    out_dir.mkdir(parents=True, exist_ok=True)

    from agent import jd_selection
    decline_list = jd_selection.load_decline_list()

    n_workers = min(RESUME_MAX_WORKERS, len(fits))
    _log_step(date_dir, {"step": "5-resumes",
                           "intent": f"generate {len(fits)} resumes ({n_workers} parallel workers)"})

    written: list[Path] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        future_to_candidate = {
            pool.submit(_generate_one_resume, c, date, date_dir, profile, out_dir, decline_list): c
            for c in fits
        }
        for fut in concurrent.futures.as_completed(future_to_candidate):
            c = future_to_candidate[fut]
            try:
                path = fut.result()
            except Exception as e:
                _log_step(date_dir, {"step": "5-resumes-thread-error",
                                       "company": c.get("company"), "error": str(e)})
                path = None
            if path and path not in written:
                written.append(path)

    _log_step(date_dir, {"step": "5-resumes", "fits": len(fits), "generated": len(written)})
    return written


# ---------- 5. Brief ----------

# Companies where the screening loop materially weights referrals — i.e.,
# coming through an internal advocate changes your probability of being
# interviewed (not just "they pay $2k if an employee refers you"). Two tiers:
#
#   REFERRAL_REQUIRED   — referrals are the dominant inbound channel. Cold
#                          applications rarely clear the recruiter screen.
#                          Hedge funds, top consulting, elite-bar startups.
#                          If you have a connection, DM them BEFORE applying.
#
#   REFERRAL_BOOSTED    — referrals significantly improve odds (typically 3–10x
#                          first-screen pass rate), but cold cracks are
#                          possible with a strong resume. Most FAANG + tier-1
#                          SaaS sit here.
#
# Match: case-insensitive substring on company name. Sister entities
# ("Goldman Sachs India", "Stripe Inc.") all hit.
#
# Curated from public signals (Glassdoor "how I got hired" threads, Blind
# referral threads, recruiter blog posts). Tier reassessed quarterly.

REFERRAL_REQUIRED = {
    # Quant / hedge funds — referral-or-bust
    "two sigma", "citadel", "jane street", "hudson river", "de shaw",
    "bridgewater", "renaissance technologies", "millennium",
    "point72", "balyasny", "jump trading", "tower research",
    # Top management consulting
    "mckinsey", "bain & company", "boston consulting group", "bcg ",
    # Elite-bar product/AI startups (small teams, founder-led, network hiring)
    "anthropic", "openai", "perplexity", "harvey", "cursor", "linear",
    "vercel", "figma", "notion", "ramp", "brex", "mercury",
    # Top PE/VC
    "sequoia", "andreessen horowitz", "a16z", "benchmark", "tiger global",
    "lightspeed", "accel partners", "kleiner perkins",
}

REFERRAL_BOOSTED = {
    # FAANG / MAANG — algo-driven screen, referrals help materially
    "google", "alphabet", "microsoft", "amazon", "apple", "meta",
    "facebook", "netflix", "nvidia",
    # Tier-1 SaaS / DevTools
    "stripe", "airbnb", "uber", "lyft", "coinbase", "pinterest",
    "dropbox", "databricks", "snowflake", "mongodb", "atlassian",
    "salesforce", "adobe", "intuit", "shopify", "twilio", "datadog",
    "confluent", "hashicorp", "cloudflare", "plaid", "doordash",
    "instacart", "asana", "discord", "gitlab", "github", "okta",
    "servicenow", "zscaler", "palantir", "scale ai",
    # Top fintech / India tier-1
    "razorpay", "cred", "zerodha", "groww", "phonepe", "navi",
    "freshworks", "postman", "browserstack", "hasura", "atlan",
    # IB tech / quant-adjacent banks
    "goldman sachs", "morgan stanley", "jpmorgan", "jp morgan",
    "deutsche bank", "barclays", "amex", "american express",
    # Streaming / consumer giants
    "spotify", "linkedin", "twitch", "wayfair", "booking",
}


def referral_culture_tag(company: str) -> tuple[str, str]:
    """Return (tag_emoji_label, plain_label) or ("", "") if neutral.

    "Required" tier emits a strong visual signal because the user is
    statistically wasting their time cold-applying there. "Boosted" tier is
    informational — "use the referral if you have one."
    """
    c = (company or "").lower()
    if any(n in c for n in REFERRAL_REQUIRED):
        return ("🔒 referral-preferred (cold apply rarely clears screen)",
                "referral-preferred")
    if any(n in c for n in REFERRAL_BOOSTED):
        return ("📈 referral boosts odds materially",
                "referral-boosted")
    return ("", "")


def build_brief(scored: list[dict], date: str, date_dir: Path,
                 resume_paths: list[Path]) -> tuple[str, str]:
    """Build brief.md + return (subject, brief_md_string)."""
    from agent.referral_lookup import (
        load_connections, find_referrals_for_company, format_referral_block,
    )

    fits = [c for c in scored if c["disposition"] == "fit"]
    bumped = [c for c in scored if c["disposition"] == "bumped_fit"]
    near = [c for c in scored if c["disposition"] == "near_miss"]
    drops = [c for c in scored if c["disposition"] == "silent_drop"]

    subject = (f"Job brief — {date} — {len(fits)} fits, {len(bumped)} bumped fits, "
                f"{len(near)} near-misses")

    raw_base = (f"https://github.com/Abhillashjadhav/Dreamjob-agent/raw/"
                f"claude/daily-runs/{date}/outputs/{date}/resumes_compact")

    connections = load_connections()
    connections_loaded = bool(connections)

    def render(c, idx, group):
        company = c["company"]
        title = c["title"]
        sc = c.get("bumped_score") or c.get("score")
        company_safe = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_") or "Unknown"
        base = f"{date}_{company_safe}_{re.sub(r'[^a-z0-9]+','-', title.lower()).strip('-')}"
        pdf_url = f"{raw_base}/{base}.pdf"
        apply_url = c.get("apply_url") or c.get("url")

        refs = find_referrals_for_company(company, connections)
        referral_line = format_referral_block(company, refs, connections_loaded)
        culture_emoji, _ = referral_culture_tag(company)
        culture_tag = f" {culture_emoji}" if culture_emoji else ""

        # Surface confidence tier honestly — score is more trustworthy when
        # scored_via=claude_cli AND jd_source=actual.
        scoring_method = c.get("scored_via", "heuristic")
        jd_source = c.get("jd_source", "title_only")
        if scoring_method in ("claude_cli", "claude") and jd_source == "actual":
            conf = "high"
        elif jd_source == "actual":
            conf = "medium (heuristic+actual JD)"
        elif scoring_method in ("claude_cli", "claude"):
            conf = "medium (claude+title-only)"
        else:
            conf = "low (heuristic+title-only)"

        bump_line = ""
        if c.get("bumped"):
            bump_line = (f"\n- **Bump rationale:** original {c['score']} → "
                         f"bumped {c['bumped_score']} via "
                         + "; ".join(c.get("bump_reasons", [])))
        audit = c.get("audit", {})
        if audit and not audit.get("skipped"):
            audit_line = (f"\n- **Audit:** {audit.get('defensible',0)} defensible, "
                          f"{audit.get('reframed',0)} reframed, "
                          f"{audit.get('fabricated',0)} fabricated ✓")
        elif audit and audit.get("skipped"):
            audit_line = (f"\n- **Audit:** skipped ({audit.get('skip_reason','?')})")
        else:
            audit_line = ""
        return (f"### {idx}. {company} — {title} ({sc}){culture_tag}\n"
                f"- **Apply:** {apply_url}\n"
                f"- **Resume PDF:** {pdf_url}\n"
                f"- {referral_line}\n"
                f"- **Score confidence:** {conf} (scored via `{scoring_method}`, "
                f"JD source `{jd_source}`)"
                f"{audit_line}\n"
                f"- **Disposition:** {group}{bump_line}\n\n")

    brief = f"# {subject}\n\n"
    # Honesty preamble — surface how many roles were scored with judgment vs heuristic.
    from collections import Counter
    methods = Counter(c.get("scored_via", "heuristic") for c in scored)
    jd_sources = Counter(c.get("jd_source", "title_only") for c in scored)
    n_judgment = methods.get("claude_cli", 0) + methods.get("claude", 0)
    n_actual_jd = jd_sources.get("actual", 0)
    brief += "## Scoring transparency\n\n"
    brief += (f"- Scored via Claude judgment: **{n_judgment}/{len(scored)}**; "
              f"heuristic-only: {methods.get('heuristic', 0)}\n")
    brief += (f"- With actual JD body: **{n_actual_jd}/{len(scored)}**; "
              f"title-only (lower confidence): {jd_sources.get('title_only', 0)}\n\n")

    brief += "## Funnel\n\n"
    from agent.scorer import FIT_THRESHOLD, NEAR_MISS_FLOOR
    brief += f"- Fits (≥{FIT_THRESHOLD} original): {len(fits)}\n"
    brief += f"- Bumped fits ({NEAR_MISS_FLOOR}-{FIT_THRESHOLD-1}→≥{FIT_THRESHOLD}): {len(bumped)}\n"
    brief += f"- Near-misses ({NEAR_MISS_FLOOR}-{FIT_THRESHOLD-1}): {len(near)}\n"
    brief += f"- Silent drops (<{NEAR_MISS_FLOOR}): {len(drops)}\n\n"

    # Subject drift flags per CLAUDE.md Hard Rule 8
    flags = []
    if methods.get("heuristic", 0) > 0 and n_judgment == 0:
        flags.append("[heuristic-only]")
    elif methods.get("heuristic", 0) > len(scored) // 2:
        flags.append("[partial-judgment]")
    if jd_sources.get("title_only", 0) > len(scored) // 2:
        flags.append("[partial-jd]")
    quarantined = [c for c in scored if c.get("disposition") == "quarantined"]
    audit_skipped = [c for c in scored if c.get("audit", {}).get("skipped")]
    if quarantined:
        flags.append(f"[fabricated-quarantine:{len(quarantined)}]")
    if audit_skipped and not quarantined:
        flags.append("[audit-partial]")
    if flags:
        subject = subject + " " + " ".join(flags)
        brief = re.sub(r"^# .*$", f"# {subject}", brief, count=1, flags=re.MULTILINE)
        brief += "\n## Drift / error notes\n\n"
        if "[heuristic-only]" in flags:
            brief += ("- `[heuristic-only]` — no Claude CLI/API available. Scores reflect "
                      "keyword-match rubric, not judgment. Add `CLAUDE_CODE_OAUTH_TOKEN` "
                      "secret to upgrade.\n")
        if "[partial-judgment]" in flags:
            brief += (f"- `[partial-judgment]` — only {n_judgment}/{len(scored)} scored "
                      "with Claude; remainder fell back to heuristic.\n")
        if "[partial-jd]" in flags:
            brief += (f"- `[partial-jd]` — only {n_actual_jd}/{len(scored)} have actual JD "
                      "bodies; rest scored on title+company only.\n")
        if quarantined:
            brief += (f"- `[fabricated-quarantine:{len(quarantined)}]` — Claude output audit "
                      f"flagged fabricated bullets in {len(quarantined)} resume(s). PDFs moved "
                      f"to `outputs/{date}/quarantined_resumes/` for manual review:\n")
            for c in quarantined:
                ad = c.get("audit", {})
                brief += (f"    - **{c.get('company')} — {c.get('title')}**: "
                          f"{ad.get('fabricated', 0)} fabricated, "
                          f"{ad.get('reframed', 0)} reframed, "
                          f"{ad.get('defensible', 0)} defensible\n")
        if "[audit-partial]" in flags:
            brief += (f"- `[audit-partial]` — output audit skipped for "
                      f"{len(audit_skipped)} resume(s) (Claude unavailable or quota).\n")
        brief += "\n"

    # Watchlist hits surface at the top of the brief regardless of FIT tier —
    # priority companies must never get buried in the NEAR-MISS pile.
    from agent.watchlist import load_watchlist, is_watchlist_match
    watchlist = load_watchlist()
    watchlist_hits = []
    if watchlist:
        for c in scored:
            if c.get("disposition") == "silent_drop":
                continue
            match = is_watchlist_match(c.get("company", ""), watchlist)
            if match:
                c["_watchlist_match"] = match
                watchlist_hits.append(c)
    if watchlist_hits:
        brief += f"---\n\n## 🎯 WATCHLIST HITS — {len(watchlist_hits)} priority-company match(es)\n\n"
        for i, c in enumerate(watchlist_hits, 1):
            sc = c.get("bumped_score") or c.get("score")
            disp = c.get("disposition", "?")
            brief += (f"### 🎯 {i}. {c['company']} — {c['title']} ({sc}, {disp})\n"
                      f"- **Apply:** {c.get('apply_url') or c.get('url')}\n"
                      f"- **Watchlist tag:** {c['_watchlist_match']}\n\n")

    if fits:
        brief += "---\n\n## FITS\n\n"
        for i, c in enumerate(fits, 1):
            brief += render(c, i, "fit")
    if bumped:
        brief += "---\n\n## BUMPED FITS\n\n"
        for i, c in enumerate(bumped, len(fits) + 1):
            brief += render(c, i, "bumped_fit")
    if near:
        brief += "---\n\n## NEAR-MISSES (no resume; gap analysis only)\n\n"
        for i, c in enumerate(near, 1):
            sc = c.get("bumped_score") or c.get("score")
            brief += (f"### {i}. {c['company']} — {c['title']} ({sc})\n"
                       f"- **Apply:** {c.get('apply_url') or c.get('url')}\n\n")

    brief += "\n— Auto-generated by dreamjob-agent\n"

    (date_dir / "brief.md").write_text(brief)
    (date_dir / "_subject.txt").write_text(subject + "\n")
    _log_step(date_dir, {"step": "9a-brief", "len": len(brief)})
    return subject, brief


# ---------- 6. Append seen-index ----------

def append_seen_index(scored: list[dict]) -> int:
    import hashlib
    out = ROOT / "outputs" / "seen_index.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    with out.open("a") as f:
        for c in scored:
            sc = c.get("bumped_score") or c.get("score") or 0
            if sc < 60:
                continue
            payload = (f"{c['company']}|{(c.get('title') or '').strip().lower()}"
                        f"|{c.get('url', '')}")
            h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            f.write(json.dumps({"hash": h, "seen_at": now,
                                  "company": c["company"], "title": c["title"],
                                  "url": c.get("url", ""), "score": sc},
                                ensure_ascii=False) + "\n")
            n += 1
    return n


# ---------- 7. Drive upload ----------

def upload_to_drive(date: str, date_dir: Path, resume_paths: list[Path]) -> dict:
    if drive_uploader is None or not os.environ.get("GDRIVE_REFRESH_TOKEN"):
        return {"skipped": True, "reason": "drive_uploader unavailable or token missing"}
    try:
        folder_id = drive_uploader.ensure_subfolder(date)
        results = []
        files = [date_dir / "brief.md", date_dir / "_scored_candidates.json"]
        files += list(resume_paths)
        for p in files:
            if not p.exists():
                continue
            try:
                r = drive_uploader.upload_file(p, folder_id)
                results.append({"name": r.get("name"), "id": r.get("id"), "ok": True})
            except Exception as e:
                results.append({"name": p.name, "ok": False, "error": str(e)})
        json.dump(results, open(date_dir / "_drive_upload_results.json", "w"),
                    indent=2, ensure_ascii=False)
        return {"folder_id": folder_id, "uploaded": sum(1 for r in results if r["ok"]),
                "failed": sum(1 for r in results if not r["ok"])}
    except Exception as e:
        return {"skipped": True, "error": str(e)}


# ---------- 8. Gmail draft ----------

def create_gmail_draft(subject: str, brief_md: str, resume_paths: list[Path]) -> dict:
    if gmail_sender is None or not os.environ.get("GMAIL_REFRESH_TOKEN"):
        return {"skipped": True, "reason": "gmail_sender unavailable or token missing"}
    try:
        out = gmail_sender.create_draft(
            subject=subject,
            body_text=brief_md,
            attachments=[str(p) for p in resume_paths],
        )
        return {"draft_id": out.get("id"), "ok": True}
    except Exception as e:
        return {"skipped": True, "error": str(e)}


# ---------- main ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    # Batch mode: slice _filtered_candidates.jsonl before scoring.
    # --score-offset N  skip the first N filtered candidates.
    # --score-limit  N  process at most N candidates (0 = no limit, process all).
    # When score-offset > 0 AND _filtered_candidates.jsonl already exists on disk
    # (from a prior batch on the same date), the fetch+filter step is skipped
    # automatically — reuses the existing file so Apify is not called again.
    parser.add_argument("--score-offset", type=int, default=0,
                        help="Skip first N filtered candidates (batch mode)")
    parser.add_argument("--score-limit", type=int, default=0,
                        help="Score at most N candidates per run (0=all)")
    # --skip-fetch: force-skip the Apify/Indeed/Gmail fetch phase even for
    # batch 1 (score_offset=0). Use when a prior date's _filtered_candidates.jsonl
    # has already been restored to the output directory by the workflow.
    # Also honoured via SKIP_FETCH_FORCE=true env var.
    parser.add_argument("--skip-fetch", action="store_true", default=False,
                        help="Skip fetch+filter; reuse existing _filtered_candidates.jsonl")
    args = parser.parse_args()
    date = args.date

    date_dir = ROOT / "outputs" / date
    date_dir.mkdir(parents=True, exist_ok=True)
    # Pipeline-integrity wrapper: any stage that produces an implausible
    # (empty / collapsed) output raises PipelineIntegrityError. We catch it
    # here, write a loud RUN_FAILED.md, and exit non-zero so the GitHub
    # Actions job is marked failed rather than silently "succeeding".
    try:
        return _run_pipeline(date, date_dir,
                             score_offset=args.score_offset,
                             score_limit=args.score_limit,
                             force_skip_fetch=args.skip_fetch)
    except invariants.PipelineIntegrityError as e:
        invariants.write_run_failed(date_dir, e)
        _log_step(date_dir, {"step": "INTEGRITY-FAIL", "stage": e.stage,
                               "expected": e.expected, "actual": e.actual,
                               "likely_cause": e.likely_cause, "decision": "halt"})
        print(f"[run_daily] INTEGRITY FAILURE [{e.stage}]: {e}", file=sys.stderr)
        return 1


def _run_pipeline(date: str, date_dir: Path,
                  score_offset: int = 0, score_limit: int = 0,
                  force_skip_fetch: bool = False) -> int:
    # Skip the expensive fetch+filter phase when:
    #   (a) score_offset > 0 — we're in batch 2-4 and batch 1 already ran, OR
    #   (b) --skip-fetch / SKIP_FETCH_FORCE=true — caller explicitly requests reuse
    #       (e.g. restoring yesterday's 290 filtered candidates to avoid re-paying
    #       for Apify when we already have a good pool from a prior date's run).
    filtered_path = date_dir / "_filtered_candidates.jsonl"
    _env_skip = os.environ.get("SKIP_FETCH_FORCE", "").lower() in ("1", "true", "yes")
    skip_fetch = ((score_offset > 0 or force_skip_fetch or _env_skip)
                  and filtered_path.exists())

    batch_label = ""
    if score_offset > 0 or score_limit > 0:
        end = (score_offset + score_limit) if score_limit else "∞"
        batch_label = f" [batch {score_offset}:{end}]"

    _log_step(date_dir, {
        "step": "0-start", "date": date,
        "intent": f"ReAct daily run: fetch → filter → enrich JDs → score → resumes → brief → notify{batch_label}",
        "score_offset": score_offset, "score_limit": score_limit,
        "skip_fetch": skip_fetch,
        "scoring_method_available": (
            "claude_cli" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
            else ("claude_api" if os.environ.get("ANTHROPIC_API_KEY")
                  else "heuristic_only")),
    })

    if skip_fetch:
        # Reuse existing _filtered_candidates.jsonl from batch 1.
        n_raw = sum(1 for l in (date_dir / "_raw_candidates.jsonl").open()
                    if l.strip()) if (date_dir / "_raw_candidates.jsonl").exists() else 0
        n_filtered = sum(1 for l in filtered_path.open() if l.strip())
        _log_step(date_dir, {"step": "1-fetch", "decision": "skip-fetch-reuse-existing",
                               "raw_on_disk": n_raw, "filtered_on_disk": n_filtered})
    else:
        _log_step(date_dir, {"step": "1-fetch", "intent": "pull Gmail alert URLs + Apify + Greenhouse"})
        gmail_urls = fetch_gmail_alert_urls(date_dir, days=3)
        # INVARIANT 1 — Gmail extraction must yield at least one URL.
        invariants.check_gmail_extraction(len(gmail_urls))
        # COMMIT 3 — test-mode refusal. Test mode skips Apify and expects zero
        # output. If Gmail nonetheless produced real URLs, a real run is
        # possible and test mode would discard genuine signal — refuse loudly.
        if _is_test_mode() and len(gmail_urls) > 0:
            _write_run_refused(date_dir, reason=(
                f"test mode on but Gmail produced {len(gmail_urls)} real job URLs "
                f"— a test run would discard genuine candidates"))
            _log_step(date_dir, {"step": "1-test-mode-refused",
                                   "gmail_urls": len(gmail_urls),
                                   "decision": "refuse-run"})
            print(f"[run_daily] RUN REFUSED — test mode on with {len(gmail_urls)} "
                  f"real Gmail URLs present", file=sys.stderr)
            return 1
        n_raw = fetch_sources(date, date_dir, gmail_urls)
        _log_step(date_dir, {"step": "1-fetch", "observation": f"{n_raw} raw rows",
                               "decision": "proceed" if n_raw else "exit"})
        if n_raw == 0:
            _log_step(date_dir, {"step": "FATAL", "reason": "no raw rows", "decision": "exit"})
            print(f"[run_daily] No raw rows for {date}. Both Apify and Greenhouse returned empty.")
            return 1
        # INVARIANT 2 — raw candidate pool must not collapse vs the Gmail signal.
        invariants.check_apify_fetch(n_raw, len(gmail_urls))

    if not skip_fetch:
        # COMMIT 4 — apify_fallback_mode enforcement.
        #   strict (default): Apify is required — 0 Apify rows is a hard failure.
        #   gmail_only: Apify intentionally skipped; scoring runs reduced-confidence.
        #   skip: Apify skipped, gated by the COMMIT 3 test-mode machinery.
        fallback_mode = os.environ.get("APIFY_FALLBACK_MODE", "strict").lower()
        if fallback_mode == "strict":
            apify_rows = _count_source_rows(date_dir, "linkedin_apify")
            if apify_rows == 0:
                raise invariants.PipelineIntegrityError(
                    stage="apify-strict-mode",
                    expected="Apify rows > 0 (apify_fallback_mode=strict)",
                    actual="0 Apify rows",
                    likely_cause=(
                        "Apify was unavailable — APIFY_TOKEN missing/invalid, the "
                        "actor errored, or it was skipped. strict mode requires "
                        "Apify. To run without it, re-dispatch with "
                        "apify_fallback_mode=gmail_only (reduced confidence)."),
                )
        _log_step(date_dir, {"step": "1-fallback-mode", "mode": fallback_mode,
                               "decision": "proceed"})

        # COMMIT 5 — ReAct Reflect substep. The post-Apify Observation is
        # "{n_raw} raw candidates". Reflect: is that consistent with the
        # trailing baseline? If raw volume collapsed, halt HERE — at the
        # post-Apify reflect point — rather than waiting for the pre-Gmail
        # anomaly checkpoint. This is the stage where a silent skip_apify
        # would first become visible.
        from agent import anomaly as _anomaly
        reflect_decision, reflect_detail = _anomaly.reflect(
            date_dir, "raw_candidates", n_raw, date)
        _log_step(date_dir, {"step": "1-reflect", "substep": "Reflect",
                               "observation": f"{n_raw} raw candidates",
                               "detail": reflect_detail,
                               "decision": reflect_decision})
        if reflect_decision == "halt":
            print(f"[run_daily] REFLECT HALT (post-Apify): raw candidate volume "
                  f"{n_raw} inconsistent with baseline — see RUN_ANOMALY.md",
                  file=sys.stderr)
            return 1

        _log_step(date_dir, {"step": "2-rule-filter",
                               "intent": "apply title/location/decline/seen filters"})
        n_filtered = run_rule_filter(date_dir)

        _log_step(date_dir, {"step": "2b-jd-enrich", "intent":
                              "fetch real JD bodies for Gmail-sourced rows via claude CLI"})
        n_jd_actual = enrich_jds(date_dir)
        _log_step(date_dir, {"step": "2b-jd-enrich", "observation":
                              f"{n_jd_actual}/{n_filtered} now have actual JD bodies"})

    # Batch slice: when score_offset / score_limit are set, trim the filtered
    # candidates file so only the requested slice enters scoring.
    if score_offset > 0 or score_limit > 0:
        import shutil as _shutil
        # Preserve the full filtered list before overwriting — batches 2-4
        # restore this file from the prior batch's branch commit so they can
        # read the correct slice rather than re-reading batch 1's truncated copy.
        all_path = date_dir / "_filtered_candidates_all.jsonl"
        if not all_path.exists():
            _shutil.copy(filtered_path, all_path)
        all_candidates = [json.loads(l) for l in all_path.open() if l.strip()]
        end_idx = (score_offset + score_limit) if score_limit else len(all_candidates)
        batch_candidates = all_candidates[score_offset:end_idx]
        # Overwrite _filtered_candidates.jsonl with just this batch's slice.
        with filtered_path.open("w") as bf:
            for c in batch_candidates:
                bf.write(json.dumps(c, ensure_ascii=False) + "\n")
        _log_step(date_dir, {
            "step": "2c-batch-slice",
            "total_filtered": len(all_candidates),
            "offset": score_offset,
            "limit": score_limit,
            "batch_size": len(batch_candidates),
            "decision": "sliced-for-batch",
        })

    _log_step(date_dir, {"step": "3-score", "intent":
                          "judgment-score each survivor (Claude CLI → API → heuristic)"})
    scored = score(date_dir)
    # INVARIANT 3 — scoring must produce at least one scored candidate.
    invariants.check_scoring(len(scored))
    resume_paths = generate_resumes(scored, date, date_dir)
    # INVARIANT 4 — if there were fits, a resume PDF must exist per fit.
    _fits_for_invariant = [c for c in scored
                           if c.get("disposition") in ("fit", "bumped_fit")]
    invariants.check_resume_generation(len(resume_paths), len(_fits_for_invariant))

    # 5b — output audit. Every generated PDF is read back, each bullet is
    # labelled defensible/reframed/fabricated against master_profile.json by
    # Claude (Max OAuth, $0). Any role with a fabricated bullet is quarantined
    # — PDF moved to quarantined_resumes/, dropped from brief/Drive/Gmail.
    # Per CLAUDE.md Hard Rule 8: do not silently degrade. The brief surfaces
    # quarantine counts in its Drift / error notes section.
    from agent import output_audit
    profile_obj = json.load(open(ROOT / "profile" / "master_profile.json"))
    react = lambda payload: _log_step(date_dir, payload)  # noqa: E731
    fits = [c for c in scored if c["disposition"] in ("fit", "bumped_fit")]
    fits_and_paths = list(zip(fits, resume_paths)) if len(fits) == len(resume_paths) else []
    if fits_and_paths:
        _log_step(date_dir, {"step": "5b-output-audit",
                               "intent": f"audit {len(fits_and_paths)} resumes for fabrication"})
        clean_pairs, audit_results = output_audit.audit_and_quarantine(
            fits_and_paths, profile_obj, date_dir, react_logger=react,
        )
        # Tag the scored entries so build_brief can render an audit column.
        company_to_audit = {a.get("company"): a for a in audit_results}
        for c in scored:
            a = company_to_audit.get(c.get("company"))
            if a:
                c["audit"] = {
                    "defensible": a.get("defensible", 0),
                    "reframed": a.get("reframed", 0),
                    "fabricated": a.get("fabricated", 0),
                    "skipped": a.get("skipped", False),
                    "skip_reason": a.get("reason", ""),
                }
        quarantined = [a for a in audit_results if a.get("fabricated", 0) > 0]
        _log_step(date_dir, {"step": "5b-output-audit-summary",
                               "total_audited": len(audit_results),
                               "quarantined": len(quarantined),
                               "audit_skipped": sum(1 for a in audit_results if a.get("skipped")),
                               "decision": "complete"})
        # Mark quarantined roles' disposition so build_brief drops them
        quarantined_companies = {q.get("company") for q in quarantined}
        for c in scored:
            if c.get("company") in quarantined_companies:
                c["disposition"] = "quarantined"
                c["quarantine_reason"] = "fabricated_bullet_detected"
        # Keep only clean PDFs in resume_paths so Drive + Gmail attach only clean.
        clean_paths_set = {p for _, p in clean_pairs}
        resume_paths = [p for p in resume_paths if p in clean_paths_set]

    subject, brief_md = build_brief(scored, date, date_dir, resume_paths)
    n_seen = append_seen_index(scored)

    # INVARIANT 5 — PDFs on disk must match the post-quarantine fit count.
    # `resume_paths` was filtered to clean (non-quarantined) PDFs above; the
    # clean fit count is the scored fits minus any quarantined disposition.
    _clean_fits = [c for c in scored
                   if c.get("disposition") in ("fit", "bumped_fit")]
    invariants.check_drive_preupload(len(resume_paths), len(_clean_fits))

    drive_result = upload_to_drive(date, date_dir, resume_paths)
    _log_step(date_dir, {"step": "9c-drive", **drive_result})

    # COMMIT 2 — rolling-baseline anomaly detection. Invariants catch
    # absolute failures (zero output); this catches relative ones — a stage
    # whose count collapsed to <30% of its trailing-7-run median even though
    # it is non-zero. Metrics are appended to data/run_metrics.jsonl every
    # run (anomalous or not) so the baseline keeps growing. On a flag we
    # halt BEFORE the Gmail draft — the Drive upload above is durable and
    # still useful for forensics; a misleading draft is not.
    from agent import anomaly
    today_metrics = {
        "gmail_urls": len(gmail_urls) if not skip_fetch else 0,
        "raw_candidates": n_raw if not skip_fetch else 0,
        "filtered": n_filtered if not skip_fetch else 0,
        "scored": len(scored),
        "fits": len(_clean_fits),
        "resumes": len(resume_paths),
    }
    anomaly_flagged = anomaly.check_anomaly(today_metrics)
    anomaly.append_metrics(today_metrics, date)
    if anomaly_flagged:
        anomaly.write_run_anomaly(date_dir, anomaly_flagged, date)
        _log_step(date_dir, {"step": "9b-anomaly-halt",
                               "flagged": anomaly_flagged,
                               "decision": "halt-before-gmail-draft"})
        print(f"[run_daily] RUN ANOMALY — halted before Gmail draft: "
              f"{anomaly_flagged}", file=sys.stderr)
        return 1

    # P3 — hard drift enforcement. Block the Gmail draft entirely if any
    # critical drift fired (fabricated bullets, heuristic-only scoring,
    # audit-skipped majority, funnel collapse). The brief is still committed
    # to git for forensics; the user just doesn't get a broken draft in
    # their inbox. Per CLAUDE.md hard rule 8: don't silently degrade.
    from agent import drift_enforcement
    audit_results_for_drift = locals().get("audit_results", []) or []
    should_block, block_reasons = drift_enforcement.evaluate_drift(
        scored=scored, n_raw=n_raw if not skip_fetch else 1,
        n_filtered=n_filtered if not skip_fetch else 1,
        resume_paths=resume_paths, audit_results=audit_results_for_drift,
    )
    if should_block:
        blocked_subject, blocked_body = drift_enforcement.build_review_required_brief(
            date=date, reasons=block_reasons, original_subject=subject,
        )
        _log_step(date_dir, {"step": "9d-drift-block",
                               "decision": "block_gmail_draft",
                               "reasons": block_reasons})
        # A blocked run intentionally attaches 0 PDFs — the invariant only
        # applies to the normal (non-blocked) delivery path.
        gmail_result = create_gmail_draft(blocked_subject, blocked_body, [])
    else:
        # INVARIANT 6 — attachment count must equal the clean fit count.
        invariants.check_gmail_predraft(len(resume_paths), len(_clean_fits))
        gmail_result = create_gmail_draft(subject, brief_md, resume_paths)
    _log_step(date_dir, {"step": "9e-gmail", **gmail_result,
                           "drift_blocked": should_block})

    from collections import Counter
    disp = Counter(c["disposition"] for c in scored)
    _log_step(date_dir, {
        "step": "10-final", "decision": "run_complete",
        "funnel": {
            "raw": n_raw if not skip_fetch else 0,
            "filtered": n_filtered if not skip_fetch else 0,
            "scored": len(scored),
            "fits": disp.get("fit", 0),
            "bumped_fits": disp.get("bumped_fit", 0),
            "near_misses": disp.get("near_miss", 0),
            "silent_drops": disp.get("silent_drop", 0),
        },
        "resumes_generated": len(resume_paths),
        "seen_index_appended": n_seen,
        "drive": drive_result, "gmail": gmail_result,
    })
    print(f"[run_daily] {date}: {n_raw if not skip_fetch else '(skip)'} raw → "
            f"{n_filtered if not skip_fetch else '(skip)'} filtered → "
            f"{disp.get('fit', 0)} fits + {disp.get('bumped_fit', 0)} bumped "
            f"+ {disp.get('near_miss', 0)} near-misses; "
            f"{len(resume_paths)} resumes; "
            f"drive={drive_result.get('uploaded', 'skip')}; "
            f"gmail={gmail_result.get('draft_id', 'skip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
