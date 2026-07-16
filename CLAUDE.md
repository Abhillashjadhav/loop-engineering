# Daily Job Search Agent — Abhillash Jadhav

## Mission
Every morning at 03:00 UTC (08:30 IST), autonomously identify 1–3 high-fit
Director PM / Principal PM / GPM roles, generate tailored resumes for ≥80%
fits, and email me the brief before 09:00 IST. Always run with full integrity
— honesty over helpfulness.

## Hard rules (do not violate)
1. **Fitment floor for resume = 80.** Below 80% don't generate a resume. 60–79% gets included as a "near-miss" with gap analysis only. Never inflate a score to clear the floor.
2. **Honesty.** Never fabricate credentials, dates, metrics, or scope.
   Strategic reframing using JD language is OK. Inventing is not.
3. **Decline list** in `profile/master_profile.json` → `decline_list_companies`.
   Skip these silently. The decline list in profile/master_profile.json is a hard ban applied at company level including all sister entities. Match case-insensitively with substring matching on the company name field.
4. **Intuit cap.** Max 3 Intuit roles in any 12-month window. Track in
   `outputs/intuit_applications.jsonl` and respect.
5. **Resume content rules** (from `profile/master_profile.json` → `constraints`):
   - Do NOT include "MJ Internet Pvt Ltd"
   - Use exact PayTM title: "AVP" (corrected 2026-05-17 — the prior "Founding product leader and PM at PayTM's B2B Retail Commerce platform" framing was an unverified inflation; "AVP" is the verified title)
   - Use exact RADAR title: "Product Advisor (Pro Bono)"
   - Frame PM experience as "11+ years of at-scale product management experience including enterprise SaaS platform products" — never "11+ years driving enterprise SaaS"
6. **Locations:** Remote (preferred), Mumbai, Bengaluru, Hyderabad. Drop everything else.
7. **India-only Indeed:** All Indeed MCP calls use `country_code: IN`. No US/EU jobs from Indeed.
8. **Don't silently fail.** If Apify returns no jobs, Gmail MCP fails, Drive MCP fails, or culture/referral data is unavailable, flag clearly in the brief subject line (`[no-apify]`, `[no-gmail]`, `[no-drive]`, `[partial-culture]`, `[LOW_COVERAGE]`) and add a "Drift / error notes" section to the brief body listing what failed and why. Never fabricate data to fill a missing field — show "data not available" instead.

## Daily loop (ReAct)

### Step 0 — Agentic ReAct loop

Every action follows think → act → observe → reflect → log:
- Think: state intent in trajectory.jsonl ({step, intent, hypothesis})
- Act: call exactly one tool (Indeed MCP, web_fetch, Drive MCP, file write, etc.)
- Observe: parse the result; record decision rationale in trajectory.jsonl ({step, observation, decision, evidence})
- Reflect: before continuing, check the observation against prior runs and the rolling baseline. Ask three questions and record the answers in trajectory.jsonl ({step, substep: "Reflect", reflection, decision}):
  1. Is this output consistent with prior runs and the trailing-7-run baseline (`data/run_metrics.jsonl`)?
  2. If not — what is the likely cause (source outage, skipped stage, filter/threshold change, genuine quiet day)?
  3. Halt or proceed? If a stage output collapsed to <30% of its baseline median, **halt now**: write `RUN_ANOMALY.md` and exit non-zero. Do not carry an implausible state downstream.
- Log: append the trajectory line. Never skip a log even on failure.

No multi-step thinking without logging. No tool call without an intent line first. **No stage output accepted without a Reflect check** — empty / collapsed pipelines are valid program states and would otherwise pass silently. The trajectory.jsonl is the agent's reasoning artifact — the run must be reconstructable from trajectory.jsonl alone, including failures, reflections, and recoveries.

### Step 1 — Fetch jobs

Greenhouse/Lever/Ashby APIs are blocked from Anthropic's Routine datacenter IP and have been disabled. Primary source is Indeed MCP via 24 query variants for max recall. Secondary source is Gmail labels (LinkedIn-Jobs, Naukri-Alerts, Hirist-Alerts) when Gmail MCP is healthy. Workday and proprietary career pages remain TODO.

1a. Run `python agent/sources/fetch_all.py --date {date}` to emit `outputs/{date}/_fetch_queue.json`. While ATS sources are disabled, this writes a no-op queue (`queue: []`) plus a `watchlist_by_ats` audit summary, and pre-creates `outputs/{date}/_fetch_responses/`. No network is touched.

1d. **Indeed MCP (primary).** Run all 24 query variants below against `country_code: IN`. Indeed has wide ingestion across companies; well-chosen queries pick up most major employers (including the ones we lost when ATS APIs were disabled). The 24 queries are organized along three axes — title × focus area, focus area depth, and company-tier signals — chosen to match the breadth of the original 106-company watchlist.

*By title × focus area (12):*

- `Director Product AI Bengaluru`
- `Director Product GenAI Mumbai`
- `Director Product Platform Hyderabad`
- `Principal Product Manager AI India`
- `Principal Product Manager GenAI Bengaluru`
- `Principal Product Manager LLM Mumbai`
- `Group Product Manager AI Bengaluru`
- `Group Product Manager Platform India`
- `Head of Product AI India`
- `Head of Product Platform Mumbai`
- `VP Product AI India`
- `VP Product Enterprise SaaS Bengaluru`

*By focus area depth (8):*

- `Principal PM Developer Productivity Bengaluru`
- `Principal PM Model Platform India`
- `Director PM Agentic AI India`
- `Director PM RAG India`
- `GPM Recommendations Bengaluru`
- `GPM Personalization India`
- `Director PM B2B Marketplace Mumbai`
- `Director PM Subscriptions India`

*By company-tier signals (4):*

- `Senior Manager Product AI India`
- `Lead Product Manager AI India`
- `Senior Principal PM India`
- `Director Engineering Product AI Bengaluru`

Run all 24 queries; expect significant overlap. Dedupe by company+normalized_title before scoring. Indeed rate-limits aggressively — if a query returns rate-limited, log to `trajectory.jsonl` and continue with the others. Goal is breadth; even partial query coverage is fine.

For each query, save raw results to `outputs/{date}/_indeed_responses/{query-slug}.json`. Then merge into `outputs/{date}/_raw_candidates.jsonl` (one Job per line, same schema as `agent/sources/greenhouse.py:Job`) with `source: "indeed"`. `agent/rule_filter.py` deduplicates `(company, normalized_title, location)` triples (preferring LinkedIn > Naukri/Hirist > Indeed; longest `description_excerpt` as tiebreaker) before applying title / location / decline-list / no-resurface filters.

1e. **Gmail job-alert labels (primary, alongside Indeed and Apify).** The user's Gmail receives daily LinkedIn alert digests at `jobalerts-noreply@linkedin.com` (occasionally `jobs-listings@linkedin.com`) and Naukri alerts at `naukrialerts@naukri.com`. Both are user-configured saved searches, so the candidates are quality-filtered at source — `gmail_linkedin` and `gmail_naukri` ride at the same tier as Indeed in `agent/rule_filter.py:SOURCE_PRIORITY`. Hirist is **not** present in this user's inbox (confirmed empty as of 2026-05-03); skip it until alerts start arriving. Don't just record the email arrived — extract the role.

**Required Gmail filter rules (apply once, in Gmail UI → Settings → Filters):**

| Sender match | Apply label |
|---|---|
| `from:(jobalerts-noreply@linkedin.com OR jobs-listings@linkedin.com)` | `JobAlerts/LinkedIn` |
| `from:(naukrialerts@naukri.com)` | `JobAlerts/Naukri` |

**Agent flow per run:**

1. Call Gmail MCP `search_threads` with `label:JobAlerts/LinkedIn newer_than:2d` (fallback: `from:jobalerts-noreply@linkedin.com OR from:jobs-listings@linkedin.com newer_than:2d` if labels aren't set up yet). Dump the raw JSON response to `outputs/{date}/_gmail_threads/linkedin.json`.
2. Repeat with `label:JobAlerts/Naukri newer_than:2d` (fallback: `from:naukrialerts@naukri.com newer_than:2d`) → `outputs/{date}/_gmail_threads/naukri.json`.
3. Wrap each label read in its own `try/except`. If Gmail MCP returns auth error, expired token, rate limit, or any other error for one label, log a non-fatal warning to `trajectory.jsonl` (e.g. `{"step":"1e","label":"JobAlerts/LinkedIn","error":"...","decision":"skip+continue"}`), skip that label, and proceed to the next one. **Do not fail the whole run on a Gmail outage.**
4. `python agent/sources/fetch_all.py --date {date}` reads those JSON files via `agent/sources/gmail_linkedin.py:fetch_jobs()` — which parses each thread's subject (`{Title} at {Company}` and the quoted-search alert format) and snippet, emits Job dicts with `source: "gmail_linkedin"` or `"gmail_naukri"`, and appends them to `outputs/{date}/_raw_candidates.jsonl`.

Cross-source dedupe runs in `rule_filter.py` against `(company, normalized_title, location)`: when the same role surfaces from Apify + Indeed + Gmail alerts (typical), the highest-priority entry wins (Apify > Indeed = `gmail_linkedin` > `gmail_naukri`); longest `description_excerpt` is the tiebreaker. Same decline-list (Step 2) applies to Gmail-sourced candidates.

(Steps 1b and 1c — the per-URL `web_fetch` loop and `parse_responses.py` consolidation — are no-ops while the ATS pipeline is disabled. The Python adapters in `agent/sources/{greenhouse,lever,ashby}.py` are intact and ready to re-enable once a transport with permitted egress is available.)

1g. **Apify LinkedIn (alongside Indeed when ATS is disabled).** LinkedIn doesn't expose a public jobs API and direct scraping is blocked from the Routine datacenter IP. The Apify actor `valig/linkedin-jobs-scraper` runs on residential infrastructure and returns structured listings via `run-sync-get-dataset-items`. `agent/sources/apify_linkedin.py` reads the token from the **`APIFY_TOKEN` environment variable** at runtime (set as a GitHub repo secret and injected by Actions / the Routine harness — the token never lands in git history). `agent/secrets/apify_config.json` carries the actor / budget / memory config; its `apify_token` field stays as the literal placeholder `REPLACE_WITH_ACTUAL_TOKEN` permanently and is only used as a fallback when the env var is absent. If neither source carries a real token, the module logs a non-fatal warning to `trajectory.jsonl` and returns `[]` — Indeed-only continues unaffected. Rotate the token at apify.com/account/integrations if compromised, then update the GitHub repo secret.

`fetch_all.py` invokes `apify_linkedin.run_all_queries()` automatically when `ATS_DISABLED=True`. The module iterates 10 strategic `(title, location)` query variants spanning {Director Product AI, Principal PM AI, GPM AI, Head of Product AI, VP Product AI, Director Product GenAI, Principal PM Platform, Director Product B2B SaaS, Principal PM Developer Productivity, Director PM Recommendations} × {India, Bengaluru, Mumbai}, enforces the `max_jobs_per_run` budget cap (default 500), and treats per-query failures (HTTP error, timeout, JSON decode) as non-fatal. Survivors get `source: "linkedin_apify"` and append to `outputs/{date}/_raw_candidates.jsonl` for shared downstream filtering. `agent/rule_filter.py` ranks `linkedin_apify` highest in `SOURCE_PRIORITY` (richer JD context than Indeed snippets), so cross-source duplicates collapse onto the LinkedIn entry.

**Coverage check (mandatory before Step 2).** After Apify (1g), Indeed (1d), and Gmail labels (1e) all complete, count total raw candidates appended to `outputs/{date}/_raw_candidates.jsonl`. Log the count to `trajectory.jsonl` as `{"step":"1-coverage", "raw_candidates": N, "by_source": {...}}`. **If N < 30**, set the run's coverage flag to `LOW_COVERAGE` — Step 9 prepends `[LOW_COVERAGE]` to the brief subject and adds a "Drift / error notes" line naming the under-delivering source(s). The run continues regardless; coverage is informational, not fatal.

### Step 2 — Rule filter (cheap, $0)
```
python agent/rule_filter.py \
    --input outputs/{date}/_raw_candidates.jsonl \
    --profile profile/master_profile.json \
    --output outputs/{date}/_filtered_candidates.jsonl
```

This drops:
- Titles not matching `(Director|Principal|Group|Head|VP).*Product`
- Locations outside Remote / Mumbai / Bengaluru / Hyderabad
- Companies in `decline_list_companies` (case-insensitive substring match on the company name field — covers sister entities)
- URLs/title-hashes seen in `outputs/seen_index.jsonl` in the last 60 days (SHA256 of `company+normalized_title+url`, truncated to 16 chars)

Expect 70–80% drop rate. Survivors typically 5–15 candidates.

### Step 3 — Score (Claude does this)

Before scoring, two-step verify each survivor: fetch the original company career page via `web_fetch` to confirm the role is still open. Drop closed/expired roles silently — portals lie, official ATS pages don't.

Then score each verified candidate 0–100 against `master_profile.json` using the rubric:

| Dimension | Weight | What to measure |
|---|---|---|
| Domain match (AI/ML/GenAI/Platform PM) | 30 | JD's primary product area vs Abhillash's focus |
| Seniority match (Director/Principal/GPM) | 20 | Title + scope; not just words |
| Location | 10 | Remote = 10, Bengaluru = 10, Mumbai/Hyderabad = 9, hybrid IN = 7 |
| Tech stack overlap | 15 | LLM/RAG/AWS/microservices/Kafka/agentic AI/devtools |
| People management vs IC | 10 | People mgmt = 10, hybrid = 7, IC = 4 |
| Comp signal | 15 | Inferred from title seniority and YOE bracket; portal salary unreliable |

Output JSON for each: `{role, company, score, why_fit (3 bullets), why_not (1 line), risks, referral_contact (from network if any)}`. Save to `outputs/{date}/_scored_candidates.json`. Honest fitment per `profile/master_profile.json` — never inflate.

**Self-check:** if you find yourself rationalizing a score above 80 to enable a resume, stop. Record the actual lower score and put it in the brief instead.

### Step 4 — Apply thresholds
- **score >= 80** → generate tailored resume + companion files (Steps 5 + 6) + ATS report (Step 7). Tag `bumped: false` in `_scored_candidates.json`.
- **60 <= score < 80** → near-miss; pass through Step 4b before final disposition
- **score < 60** → silent drop

### Step 4b — Adjacent-skill bump for near-misses (60–79%)

For every candidate scored 60–79 in Step 4, attempt one re-scoring pass that re-weights adjacent / transferable skills documented in `profile/master_profile.json`. Examples of legitimate adjacency:

- Director PM, Promotions / Pricing → Amazon Promotions Platform experience (4 yrs, $4B GMS)
- Principal PM, Trust & Safety / Governance → Wayfair Model Proxy / governance layer ownership
- GPM, Recommendations / Personalization → Amazon AI/ML recommendation engine ($1.2B annualized) and CTL personalization platform ($3.2B GMV)
- Director PM, B2B Marketplace / Subscriptions → PayTM B2B Payments + IndiaMart Big Brands subscriptions
- Principal PM, Developer Productivity / Platform → Wayfair GenAI dev platform (2,800+ engineers, $300M impact)

Bump rules:
- **Maximum +20 points uplift** in a single bump. Hard cap (raised from +15 on 2026-06-18 so the *entire* 60–79 near-miss band can reach the 80 apply-floor when adjacency is genuine — a 60 needs +20). The bump is the **sum of matched, documented adjacency signals** (each tied to a real `master_profile.json` bullet), capped at +20: a role matching several of Abhillash's real strengths bumps more than one matching a single weak adjacency, and a role matching none does not bump at all. The cap — not inflation — keeps this honest.
- **Only roles that reach 80 (original OR bumped) get a resume and enter the apply set.** A 60–79 role whose bump still leaves it <80 stays a near-miss: gap analysis only, no resume, not applied to.
- Only apply when the JD asks for a skill genuinely adjacent to a documented Abhillash bullet. **Inventing adjacency is forbidden** — same honesty rule as scoring. No matching signal → no bump.
- Document on each candidate in `outputs/{date}/_scored_candidates.json`: `{original_score, bumped_score, adjacent_skills_applied: ["..."], rationale, bumped: true|false}`.
- If `bumped_score >= 80`, treat the role as a fit going forward (Steps 5–7) with `bumped: true`. Step 9 lists it under **BUMPED FITS**.
- If the bump still leaves the role <80, leave it as a near-miss (Step 9 NEAR-MISSES section, gap analysis only, no resume).

### Step 4c — Culture lookup via Indeed MCP (replaces blocked web fetch)

Glassdoor / Levels.fyi / company career pages return HTTP 403 from the Routine sandbox firewall. Indeed MCP `get_company_data` carries the same employee-review aggregate (overall rating, sub-ratings for culture / WLB / management / compensation / advancement, would-recommend %, CEO approval, interview signal) and IS reachable, so it replaces the web-fetch path.

For each fit (original ≥80 or bumped ≥80), call:
```
get_company_data(
    companyName="{Company}",
    language="en",
    location={"country": "IN" if Indian role else "US", ...},
    knowledgeCategories={"metadata": True, "ratings": True, "salaries": False},
)
```

Then run the response through `agent/culture_lookup.py:format_culture_snapshot()`. The snapshot is `{available, one_liner, details}`:
- `one_liner` — the brief's one-line culture summary (e.g. `"Indeed 3.8/5 (31 reviews) — 55% would recommend (strong culture 3.8, weak comp 3.4)"`)
- `details` — full sub-ratings dict (culture, WLB, management, compensation, advancement, CEO approval %, review count, Indeed page URL)

Render via `format_brief_block(snapshot)` — emits the headline plus a compact "culture X.X · WLB X.X · mgmt X.X · comp X.X · advancement X.X · CEO approval N% · [Indeed page](url)" line under it.

If `available=False` (Indeed has no review aggregate for that company — common for very small/new shops): brief shows `"culture data not available"` and the run adds a `[partial-culture]` flag to the subject line per Hard Rule 8. **Never fabricate ratings.**

### Step 4d — Referral lookup via LinkedIn connections CSV

The user exports their LinkedIn connections (LinkedIn → Settings → Data Privacy → Get a copy of your data → **Connections only**) and commits the resulting CSV to `data/linkedin_connections.csv`. The export's standard preamble (2–3 explanatory lines) is tolerated by `agent/referral_lookup.py:_open_skipping_preamble`.

For each fit, call:
```
from agent.referral_lookup import load_connections, find_referrals_for_company, format_referral_block
conns = load_connections()
matches = find_referrals_for_company("{Company}", conns)
brief_line = format_referral_block("{Company}", matches, connections_loaded=bool(conns))
```

Match rule: case-insensitive substring on the connection's `Company` column — same as the decline-list match in `rule_filter.py`, so sister entities (e.g. "Experian Services Pvt Ltd" matches `Experian`) all hit. Cap at 5 matches per company so one megacorp doesn't crowd the brief.

Three output states:
1. **CSV missing** → brief shows `"no referral path identified (no LinkedIn connections export in repo)"`
2. **CSV present, no match** → `"no 1st-degree connections at {Company}"`
3. **Matches** → `"{Name} ({Title}) — {LinkedIn URL}"`, joined by `;`

**Never make up names.** Re-export the CSV monthly to keep referrals current.

### Step 5 — Resume generation (every fit — original ≥80 OR bumped ≥80)

For each role with `score >= 80` (original) OR `bumped_score >= 80` (post Step 4b), in order:

a) Resume content is sourced from `profile/master_profile.json`. The preferred generator is the LLM generate → critique → iterate loop in `agent/llm_resume_generator.py` (see "Resume generation: LLM critique-and-iterate" below). It needs the Claude CLI (`CLAUDE_CODE_OAUTH_TOKEN`) and a real JD body; when either is missing, generation falls back to the deterministic `agent/resume_pipeline.py` renderer so the daily run never blocks.
b) Render the PDF with ReportLab per the layout spec in `agent/resume_pipeline.py` (`build_pdf_from_draft` for the LLM path, `build_pdf` for the fallback):
   - A4, margins 0.58" L/R, 0.48" T/B
   - Helvetica, embedded fonts (Liberation Serif fallback)
   - 48–50 KB target file size (8–12 KB indicates unembedded fonts → regenerate)
   - Page 2 target 3,400–4,200 chars
   - Bold keywords matching the JD
   - KeepTogether blocks per role
c) Strategic reframing with JD language is allowed. Fabrication is not.
d) **Output filename: `outputs/{date}/resumes/{date}_{Company}_{role-slug}.pdf`** — date-stamped so the file is identifiable when downloaded or attached. Use the run `{date}` (the same value used in the parent dir), not `datetime.now()`. Example: `outputs/2026-05-02/resumes/2026-05-02_Microsoft_principal-pm-trust-safety.pdf`.

e) **Verify PDFs are committed to git after generation.** `outputs/*/resumes/*.pdf` is tracked (the `.gitignore` exclusion was removed on 2026-05-03 after a Drive-upload run discovered the previous day's PDFs were never persisted). Run `git status outputs/{date}/resumes/` before Step 9; every fit's PDF must show as either tracked-clean or to-be-committed. If any are missing or untracked-but-unstaged, `git add outputs/{date}/resumes/*.pdf` and stage them in the daily-run commit. Step 9c's Drive sync depends on the PDFs existing on disk; Gmail draft attachments (where supported) and the brief's resume links both break if the PDFs aren't there in tomorrow's session.

### Step 6 — Generate companion files (one set per ≥80% fit)

For each resume produced in Step 5, write three companion files into the same `outputs/{date}/resumes/` directory, all date-stamped to match:

- `{date}_{Company}_{role-slug}_gap_analysis.md` — 3–5 lines on JD asks not emphasized in the profile
- `{date}_{Company}_{role-slug}_crisp_answers.json` — `{why_this_role, why_now, notice_period, comp_expectation}`, copy-paste-ready, no hedging
- `{date}_{Company}_{role-slug}_interview_prep.md` — 5 likely questions + evidence-based answer outlines drawn from `master_profile.json`

### Step 7 — ATS readiness report

For each generated resume, run:

```
python agent/ats_report.py \
    --resume outputs/{date}/resumes/{date}_{Company}_{role-slug}.pdf \
    --jd <jd-text-or-path> \
    --output outputs/{date}/ats_reports/{date}_{Company}_{role-slug}_ats.json
```

This produces parseability checks (embedded fonts, single column, standard headers, dates), keyword coverage vs JD (matched, missing critical, missing nice-to-have), and overall pass-likelihood per ATS family. If parseability < 85 or keyword coverage < 70, regenerate (max 2 retries) — flag missing critical keywords that could be authentically added by reframing real experience.

### Step 8 — Append surfaced hashes to outputs/seen_index.jsonl

After surfacing a role in the brief (whether ≥80% fit or 60–79% near-miss), compute its hash (SHA256 of `company+normalized_title+url`, truncated to 16 chars) and append a line to `outputs/seen_index.jsonl`:

```json
{"hash": "<16-char hex>", "seen_at": "<ISO-8601 UTC>", "company": "...", "title": "...", "url": "...", "score": 0-100}
```

Step 2's no-resurface check reads this file with a 60-day window — adding the hash here is what prevents the same role from re-appearing tomorrow.

### Step 9 — Compose brief and deliver

9a. Write `outputs/{date}/brief.md` and `outputs/{date}/brief.html`. **Brief structure (mandatory — three groups in this order):**

1. **FITS** — original score ≥80. For each: company, role, score, why-fit (3 bullets), why-not (1 line), apply link, **resume PDF link** (date-stamped filename), **referral path** (LinkedIn-first), **culture snapshot** (Indeed), ATS readiness summary.
2. **BUMPED FITS** — original 60–79 but bumped to ≥80 via Step 4b. Same artifacts as FITS plus a "Bump rationale" line: `original {N} → bumped {M} via [adjacent skills applied]`.
3. **NEAR-MISSES** — remaining 60–79 (no bump, or bumped score still <80). Gap analysis only. No resume, no culture, no referral.

For every entry under FITS or BUMPED FITS:

For every entry under FITS or BUMPED FITS — **render Referral path BEFORE Culture snapshot** (LinkedIn signal leads):

- **Referral path:** any LinkedIn 1st-degree connections from `data/linkedin_connections.csv` (per Step 4d). If the file is absent: `"no referral path identified (no LinkedIn connections export in repo)"`. If present but no match: `"no 1st-degree connections at {Company}"`. Don't make up names.
- **Culture snapshot:** Indeed rating + one-line summary via Step 4c (`agent/culture_lookup.py`). Format: `"Indeed 3.8/5 (31 reviews) — 55% would recommend (strong culture 3.8, weak comp 3.4)"` plus a sub-rating breakdown line. If Indeed has no aggregated review data, write the literal string `"culture data not available"` and add a `[partial-culture]` flag to the subject line. **Never fabricate.**
- **Resume PDF link:** markdown link in the format `[YYYY-MM-DD_Company_role-slug.pdf](resumes/YYYY-MM-DD_Company_role-slug.pdf)` so the GitHub-rendered brief points at the file in the same commit.

**Subject-line construction:** `Job brief — {date} — {N_FITS} fits, {N_BUMPED} bumped fits, {M} near-misses` plus drift flags appended in this order when applicable: `[LOW_COVERAGE]`, `[no-apify]`, `[no-gmail]`, `[no-drive]`, `[partial-culture]`. If multiple flags, concatenate with single spaces.

**Drift / error notes section:** If any flag fired, the brief opens with a `## Drift / error notes` section listing each failure mode with one line of context (e.g. "Apify returned 0 jobs — token request failed with HTTP 401, see trajectory step 1g"). Honest visibility, not silent degradation.

Commit all artifacts (brief, candidates.json, trajectory.jsonl, resumes/, ats_reports/) to branch `claude/daily-runs/{date}` and push. **This is the durable delivery channel.**

9b. Run `python agent/notifier_drive.py --build-manifest --date {date}` to enumerate the files for Drive sync. This writes `outputs/{date}/_drive_upload_manifest.json`. Globs in `notifier_drive.py` (`resumes/*.pdf`, `resumes/*_gap_analysis.md`, etc.) match the date-stamped filenames without modification.

9c. Read the manifest. For each entry:
   - If date sub-folder doesn't yet exist under parent folder, call Drive MCP `create_file` to create it (mime: `application/vnd.google-apps.folder`, parent: `parent_folder_id`). Capture its ID.
   - Then call Drive MCP `create_file` for each file in the manifest with parent set to the date sub-folder ID. Use the `mime_type` from the manifest. The `drive_name` is the local filename — date prefix is preserved on upload.
   - On per-file failure, log and continue. On total Drive MCP unavailability, log warning and skip — git push from 9a is durable.

9d. Run `python agent/notifier_drive.py --record-results --date {date}` to log all upload outcomes to `outputs/{date}/_drive_upload_results.json`. Pipe the results JSON list (one entry per file: `{local_path, drive_id, drive_url, status}`) on stdin, or pass `--results-file <path>`.

9e. **Gmail delivery (re-enabled).** Create a Gmail draft via `Gmail.create_draft` MCP with the brief subject (from above), body = the `brief.md` content rendered to plain text, and attachments = every PDF in `outputs/{date}/resumes/`. If Gmail MCP fails (auth / rate limit / oversized payload), log a non-fatal warning to `trajectory.jsonl`, append `[no-gmail]` to the subject line of the still-pushed brief on GitHub, and continue. Drive sync (9b–9d) and git push (9a) remain the durable channels regardless.

Drive is the user-facing channel; Gmail is the morning notification; git push is the durable backup.

### Step 10 — Finalize trajectory and run summary

Append a final summary line to `outputs/{date}/trajectory.jsonl` capturing the funnel: raw candidates → after dedupe → filtered → verified → scored → fits (≥80) → near-misses (60–79) → resumes generated → companions → ATS reports → drive uploads (ok / failed). One line, JSON object, `step: "10"`, `decision: "run_complete"` (or `"run_complete_with_warnings"` if any non-fatal failures were logged earlier in the run).

The trajectory.jsonl from Step 0 onward must be self-contained: someone reading it cold (per `eval/judge_prompt.md`) should be able to reconstruct every decision the agent made today, including which warnings fired, which sources were skipped, and which roles were dropped at which stage.

## Resume generation: LLM critique-and-iterate

`agent/llm_resume_generator.py` generates each resume through an LLM generate → critique → iterate loop. The meta-goal: a resume that makes a recruiter pick up the phone for a strong-fit role. When a design choice helps audit tidiness but hurts call-back odds, call-back odds win.

**Three stages**, all driven by Claude via the `claude` CLI (Max-plan OAuth, $0):

1. **Generator** (`generate_draft`) — a `master_profile.json` digest + the JD → a resume draft (executive summary, per-role X-Y-Z bullets, core skills, core competencies).
2. **Critic** (`critique_draft`) — JD + draft → a per-bullet critique scoring each bullet 1–5 on six dimensions, plus a 0–100 fitment score:
   - `jd_intent_match` — speaks to what THIS JD wants, not generic PM work
   - `outcome_specificity` — concrete outcome; strong, role-distinct lead verb
   - `mechanism_credibility` — X-Y-Z: the "how" is present and believable
   - `scale_legibility` — numbers/scope legible in a 6-second scan
   - `tone_fit` — matches the seniority the JD implies; no hype, no under-sell
   - `fabrication_trace` — every claim traces to `master_profile.json`
3. **Iteration controller** (`iterate`) — generate, critique, apply, re-critique, up to **3 rounds** OR until the fitment delta between consecutive rounds drops below **5**. The highest-fitment draft ships.

**Hybrid fabrication check** (`fabrication_check`) runs every round:
- Layer 1 (deterministic): every numeric token in every bullet must appear verbatim somewhere in `master_profile.json` — an untraced number is an automatic `unverifiable`.
- Layer 2 (LLM): a claim-classification pass labels each bullet `traced` / `jd_adjacent` (a real fact reframed into JD vocabulary — allowed) / `unverifiable` (fabrication).

`unverifiable` claims are fed back as critique and never ship. Every generated PDF gets a `<stem>.ledger.md` output ledger recording the per-round fitment and the per-bullet trace classification.

**Honesty** (Hard Rule 2): the generator may only restate facts present in `master_profile.json`. Reframing into JD vocabulary is encouraged; inventing metrics, scope, dates, headcount, or budget is forbidden. If the JD wants something the profile cannot support, the gap is left honest — not papered over.

`agent/output_audit.py` is the post-generation backstop: it reads every PDF back and labels each bullet `defensible` / `reframed` / `fabricated`; any resume carrying a fabricated bullet is quarantined and dropped from the brief, Drive sync, and Gmail draft, with the quarantine count surfaced in the brief's Drift / error notes section.

## Edge cases

- **Zero ≥80% matches:** still send the email. Subject becomes "{date} — no fits today, {M} near-misses." Don't manufacture fits.
- **Indeed MCP empty/error:** retry once with broader query. If still empty, log and continue. Don't block the run.
- **Greenhouse 404 on a slug:** mark that company `confidence: low` in `target_companies.yaml`, log, continue. Discovery script will reverify weekly.
- **Resume generator failure on one fit:** still send the brief; flag the failure; don't fail the whole run.
- **Suspected Intuit application count >= 3 in last 12 months:** still surface the role in the brief, but flag clearly: "Intuit cap — verify before applying." Don't auto-generate the resume.
- **Tempted to inflate fitment to clear 80?** Don't. Send "no fits today" instead. Honesty over output.

## Silent-failure invariants

**Empty pipelines are valid *program* states and therefore invisible.** A run that produces zero candidates, zero resumes, and an empty Drive folder throws no exception — historically it "succeeded". `skip_apify=True` once did exactly that. The pipeline now enforces *plausibility* of outputs, not just absence of exceptions. Bypass flags that degrade output must be **loud, not silent**.

Three distinct halt artifacts are written into `outputs/{date}/` and committed to the daily-runs branch:

| Artifact | Meaning | Written by |
|---|---|---|
| `RUN_FAILED.md` | A stage produced an implausible (empty / collapsed) output | `agent/invariants.py` |
| `RUN_ANOMALY.md` | A stage's count collapsed to <30% of its trailing-7-run baseline | `agent/anomaly.py` |
| `RUN_REFUSED.md` | The orchestrator declined to run — self-contradictory config | `agent/run_daily.py` |

**`agent/invariants.py` — output-integrity invariants.** `PipelineIntegrityError` is raised by six stage checks: Gmail extraction (>0 URLs), source fetch (raw >= 50% of Gmail URLs), scoring (>0 scored), resume generation (one PDF per fit — conditional, 0 resumes is fine when there are 0 fits), Drive pre-upload (PDF count == clean fit count), Gmail pre-draft (attachments == fit count). `run_daily.main()` catches it, writes `RUN_FAILED.md`, exits non-zero.

**`agent/anomaly.py` — rolling-baseline anomaly detection.** Stage counts append to `data/run_metrics.jsonl` every run. `check_anomaly` (pre-Gmail backstop) and `reflect` (per-stage, ReAct substep) flag any stage <30% of its trailing-7-run median; on a flag the run writes `RUN_ANOMALY.md` and halts.

**Workflow inputs (renamed for loudness).** `skip_apify` is gone. To skip Apify you now choose `apify_fallback_mode`:
- `strict` (default) — Apify required; 0 Apify rows is a hard `RUN_FAILED`.
- `gmail_only` — Apify skipped deliberately; scoring runs via `agent/gmail_only_scorer.py` at reduced confidence and a lowered fit threshold (60); every candidate carries `reduced_confidence: True`.
- `skip` — Apify skipped; gated by the test-mode confirmation below.

`test_mode_no_apify_zero_output_expected` + `confirm_test_mode` — test mode is double-gated: a scary-named input plus a separate confirmation, a preflight failure if unconfirmed, a `⚠️ TEST MODE` label in the Actions run name, and an orchestrator refusal (`RUN_REFUSED.md`) if real Gmail signal exists.

## What NOT to do
- Don't search LinkedIn directly. Use Gmail labels for LinkedIn alerts only.
- Don't include MJ Internet Pvt Ltd in any resume.
- Don't use generic placeholder metrics. Every number must be from `master_profile.json`.
- Don't write narrative summaries for the email — be crisp, one-liners, copy-paste-ready.
- Don't reformat the resume template. Use the existing skill spec exactly.
- Don't run more than once per day unless explicitly triggered manually via "Run now".
