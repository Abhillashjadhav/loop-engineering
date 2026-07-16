# Daily Job Search Agent — Abhillash Jadhav

Autonomous Director PM / Principal PM / GPM job search, running daily at
08:30 IST on Anthropic's cloud (Claude Code Routine). No laptop required.

## Daily autonomous flow

1. Routine fires at 8:30 AM IST (claude.ai/code/routines, "Daily job search")
2. Agent runs ReAct loop: fetch (Indeed MCP) → rule filter → score → resumes for ≥80% fits → companion files → ATS reports → brief
3. Pushes everything to branch `claude/daily-runs/{date}` on this repo
4. Mirrors brief + PDFs + companions to user's Drive folder "Dream job Agent/{date}/" via manifest pattern
5. GitHub Pushes email notification fires to user's inbox
6. User opens email → taps branch link OR opens Drive folder → reads brief, downloads PDFs, applies

Daily output appears by 8:40 AM IST. No manual triggering required.

## File naming

All resume PDFs and companion files are date-stamped with the run date so they remain identifiable when downloaded or attached to emails:

- Resume:           `{YYYY-MM-DD}_{Company}_{role-slug}.pdf`
- Gap analysis:     `{YYYY-MM-DD}_{Company}_{role-slug}_gap_analysis.md`
- Crisp answers:    `{YYYY-MM-DD}_{Company}_{role-slug}_crisp_answers.json`
- Interview prep:   `{YYYY-MM-DD}_{Company}_{role-slug}_interview_prep.md`
- ATS report:       `{YYYY-MM-DD}_{Company}_{role-slug}_ats.json`

Example: `2026-05-02_Microsoft_principal-pm-trust-safety.pdf`

## Output locations

Per run:
- GitHub branch: `claude/daily-runs/{date}`
- Drive folder: `Dream job Agent/{date}/`
- Local in branch: `outputs/{date}/brief.md`, `outputs/{date}/resumes/*.pdf`, `outputs/{date}/ats_reports/`, `outputs/{date}/trajectory.jsonl`, `outputs/{date}/_drive_upload_manifest.json`, `outputs/{date}/_drive_upload_results.json`

> **Note (2026-05-01):** Greenhouse / Lever / Ashby ATS APIs are disabled — they return HTTP 403 from Anthropic's Routine datacenter IP via both direct HTTP and `web_fetch`. The ATS Python adapters in `agent/sources/{greenhouse,lever,ashby}.py` are kept intact and will be re-enabled once a transport with permitted egress is available. See `CLAUDE.md` Step 1 for the current flow.

## Setup (~1 hour, one-time)

### 1. GitHub repo
```bash
gh repo create abhillash-job-agent --private
git remote add origin https://github.com/Abhillashjadhav/abhillash-job-agent.git
git push -u origin main
```

### 2. Connect MCPs in Claude.ai
You need these connected for the agent to work:
- ✅ Indeed (already connected — verify `country_code: IN` in calls)
- ⬜ Gmail (for sending the daily brief)
- ⬜ Google Drive (optional — for resume backups)

Optional: a Telegram bot if you want mobile push for runs that need review.

### 2a. Setting up Apify LinkedIn

LinkedIn doesn't expose a public jobs API and direct scraping is blocked from the Routine datacenter IP. The agent uses the Apify actor `valig/linkedin-jobs-scraper` (residential proxy infrastructure) via the `run-sync-get-dataset-items` endpoint. The token is read from a **GitHub repo secret** at runtime — it never gets committed to git.

1. Sign up at [apify.com](https://apify.com) (free tier: $5/mo credit — covers ~10 daily runs of 50 rows each).
2. **Settings → Integrations → Personal API tokens → Create token** (name: `dreamjob-agent`). Copy the token (looks like `apify_api_xxxxxxxxxxxx`).
3. In GitHub: this repo → **Settings → Secrets and variables → Actions → New repository secret**.
4. **Name:** `APIFY_TOKEN`, **Value:** paste the Apify token, **Save**.
5. Verify by triggering Routine **"Run now"** — check `outputs/{date}/trajectory.jsonl` for `"linkedin_apify"` entries (no `"no real token"` warning).

**How the token is resolved at runtime:**
1. `APIFY_TOKEN` env var (set via GitHub repo secret / Actions runtime) — preferred.
2. Fallback: `apify_token` field of `agent/secrets/apify_config.json`. In normal operation this stays as the literal placeholder `REPLACE_WITH_ACTUAL_TOKEN` permanently — the file only carries `actor_id`, `max_jobs_per_run`, `memory_mb`.

**Safety:** if neither source carries a real token, `agent/sources/apify_linkedin.py` logs a non-fatal warning to `trajectory.jsonl` and the agent falls back to Indeed-only. The daily run never fails because Apify is unconfigured.

**Rotation:** revoke at apify.com/account/integrations → generate a new one → update the `APIFY_TOKEN` GitHub repo secret. No file edits, no commits.

The 10 query variants the agent runs daily live in `agent/sources/apify_linkedin.py:LINKEDIN_QUERIES` — edit that list to retune coverage.

### 3. Set up Gmail filters
Create labels and filters so LinkedIn/Naukri/Hirist alerts get tagged:
- Label `LinkedIn-Jobs` ← `from:jobs-noreply@linkedin.com`
- Label `Naukri-Alerts` ← `from:*@naukri.com`
- Label `Hirist-Alerts` ← `from:*@hirist.com`
- Label `Recruiter-Forwards` ← any forwarded recruiter messages

The agent's Gmail MCP step reads these labels every morning.

### 4. Create the Routine
Go to https://claude.ai/code/scheduled
- Click **New Routine** → **Cloud**
- Connect this GitHub repo as the working directory
- Schedule: `0 3 * * *` (UTC = 08:30 IST)
- Prompt: `"Run the daily job search per CLAUDE.md."`
- Permissions: allow bash, web_fetch, Gmail MCP, Indeed MCP, git
- Save

### 5. Manual dry run before activating
Click **Run now** at least 3 times across different days. Watch:
- Does it find your watchlist companies correctly?
- Does the rule filter drop the right things?
- Are scores honest (not inflated)?
- Does the email actually land in your inbox?

Only after 3 clean runs, leave it on autopilot.

## Daily output

Daily output lands at: (a) GitHub branch `claude/daily-runs/{date}` (durable), (b) Google Drive folder `Dream job Agent/{date}/` (user-facing — preferred for daily use). Gmail MCP has been removed from the daily flow (token expiry / app-blocked errors); per-file Drive failures are non-fatal and the git push is the durable fallback.

The brief looks like:

> **Subject: Job brief — 2026-04-27 — 2 fits, 3 near-misses**
>
> **Top fits (≥85%, resume attached):**
> - **Airbnb** — Principal PM, AI Platform — 88% — *resume attached* — ATS: Greenhouse parseability 95, keyword coverage 82, missing critical: MLOps, evaluation pipelines — Apply: [link] — Referral: none
> - **Anthropic** — Group PM, Developer Platform — 91% — *resume attached* — ATS: Greenhouse parseability 98, keyword coverage 89 — Apply: [link] — Referral: Aayush Chourasia
>
> **Near-misses (70–84%, gap analysis):**
> - Stripe — Director PM, Payments — 78% — *gap: payments domain depth*
> - Notion — Principal PM, AI — 73% — *gap: B2C product-led growth metrics*
>
> Full brief in repo: `outputs/2026-04-27/brief.md`

## Maintenance

- **Weekly:** review `eval/eval_results/` to spot trajectory regressions
- **Monthly:** mark applied roles in `outputs/applications.jsonl` (Apply / Skip / Reject) — feeds back into score calibration
- **Quarterly:** add new companies to `profile/target_companies.yaml`; the discovery script auto-detects ATS

## Cost

Included in your Claude Max 20x subscription. Daily run consumes ~150–250K
tokens — well under 5% of weekly quota. No surprise bills.

## Files of note

| File | Purpose |
|---|---|
| `CLAUDE.md` | Agent prompt — the brain of the system |
| `architecture.md` | Design doc with rationale for every choice |
| `profile/master_profile.json` | Career data — single source of truth |
| `profile/target_companies.yaml` | Watchlist with ATS slugs |
| `agent/sources/*.py` | ATS clients (Greenhouse, Lever, Ashby) |
| `agent/rule_filter.py` | Cheap pre-LLM filtering |
| `agent/ats_report.py` | Honest parseability + keyword coverage |
| `eval/judge_prompt.md` | LLM-as-judge for trajectory + output |
| `outputs/{date}/` | Daily artifacts (brief, resumes, trajectory) |

## Honesty rails

The agent is explicitly forbidden from:
- Fabricating credentials, dates, metrics, or scope
- Inflating fitment scores to clear the 85% floor
- Including MJ Internet Pvt Ltd in any resume
- Using "11+ years driving enterprise SaaS" framing (must be "11+ years of at-scale PM including enterprise SaaS")
- Searching LinkedIn directly (use Gmail-piped alerts only)

If the agent ever produces output that violates these, the LLM-as-judge will
catch it and downgrade the run to "ship_to_user: false" — you'll get a
review-required alert instead of an auto-sent email.
