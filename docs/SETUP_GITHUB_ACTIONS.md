# Setup: Daily Job Search Pipeline (GitHub Actions automation)

One-time setup. After this, the pipeline runs **autonomously every day at 03:00 UTC (08:30 IST)**:

1. **Reads your Gmail JobAlerts/LinkedIn label** for the last 3 days, extracts every LinkedIn job URL from the digest emails
2. **Sends those URLs to Apify** (`valig/linkedin-jobs-scraper` in URL-targeted mode) → gets the full JD body for each role
3. **Also runs 10 query-based broad searches** for breadth (catches roles you didn't get an alert for)
4. **Filters, scores, and tailors a resume PDF per role** using the actual JD content
5. **Drops a Gmail draft + Drive folder** with brief + per-role tailored PDFs and apply links

Your job: open the Gmail draft, click each role's apply link, attach the matching PDF, submit. **No copy-paste of dataset files. No tailoring resumes manually. No re-uploading anywhere.**

Total setup time: **~15 minutes**. You only do this once.

---

## What you'll set up

A GitHub Actions workflow that, every morning, calls Apify → filters → scores → generates resumes → uploads to your Drive → drops a Gmail draft. No copy-paste from then on.

---

## Step 1 — Create OAuth credentials (one-time, ~5 min)

You need OAuth client credentials so GitHub Actions can use your Gmail and Drive accounts on your behalf.

### 1.1 Create a Google Cloud project

1. Go to https://console.cloud.google.com/projectcreate
2. Project name: `dreamjob-agent` (or anything). Click **Create**.

### 1.2 Enable the APIs

1. https://console.cloud.google.com/apis/library/gmail.googleapis.com → **Enable**
2. https://console.cloud.google.com/apis/library/drive.googleapis.com → **Enable**

### 1.3 Configure the OAuth consent screen

1. https://console.cloud.google.com/apis/credentials/consent
2. User Type: **External** → Create
3. App name: `dreamjob-agent` · User support email: yours · Developer contact: yours · **Save & Continue**
4. **Scopes** screen: click **Add or Remove Scopes**, paste these scope URLs separated by spaces:
   - `https://www.googleapis.com/auth/gmail.compose` (write drafts)
   - `https://www.googleapis.com/auth/gmail.readonly` (read JobAlerts/LinkedIn label)
   - `https://www.googleapis.com/auth/drive.file` (write Drive)
   - `openid` (required for refresh tokens)
   - Click **Save & Continue**
5. **Test users** screen: add your own Gmail address (`abhilashjadhav@gmail.com`) → **Save & Continue** → **Back to Dashboard**
6. (Optional) Click **Publish App** to skip the test-users restriction. For personal use the test-user route works fine.

### 1.4 Create OAuth client credentials

1. https://console.cloud.google.com/apis/credentials
2. **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app** · Name: `dreamjob-agent-cli`
4. Click **Create** → **Download JSON** (save it temporarily)

Open the downloaded JSON, you'll see two values you need:
```json
{ "installed": { "client_id": "xxx.apps.googleusercontent.com", "client_secret": "GOCSPX-yyy", ... } }
```

You'll use these as **the same client_id/client_secret for both Gmail and Drive** (one OAuth client can mint tokens for multiple scopes).

---

## Step 2 — Mint refresh tokens (one-time, ~3 min)

A refresh token is what GitHub Actions uses each morning to get fresh access tokens — no interactive login required.

### 2.1 Open the Google OAuth Playground

https://developers.google.com/oauthplayground/

### 2.2 Configure it to use YOUR client

1. Top-right **⚙ gear icon** → check **Use your own OAuth credentials**
2. Paste your **OAuth Client ID** and **OAuth Client secret** from Step 1.4 → close the panel

### 2.3 Authorize all 3 scopes and exchange for tokens

1. In the left "Step 1" box:
   - Scroll to **Gmail API v1** → check `https://www.googleapis.com/auth/gmail.compose` AND `https://www.googleapis.com/auth/gmail.readonly`
   - Scroll to **Drive API v3** → check `https://www.googleapis.com/auth/drive.file`
2. Click **Authorize APIs** → sign in as `abhilashjadhav@gmail.com` → grant access
3. After redirect, click **Exchange authorization code for tokens**
4. Copy the **Refresh token** value (long string starting with `1//`). This is your `GMAIL_REFRESH_TOKEN` AND `GDRIVE_REFRESH_TOKEN` (same value works for both — one token, three scopes).

### 2.4 Get your Drive parent folder ID

1. In Drive, navigate to the **`Dream job Agent`** folder you created
2. Look at the URL: `https://drive.google.com/drive/folders/19_Z4ymdCgwenwQ-JdFM-NLqqY8J263Sv`
3. The string after `folders/` is your `GDRIVE_PARENT_FOLDER_ID`. (For your account it's `19_Z4ymdCgwenwQ-JdFM-NLqqY8J263Sv`.)

---

## Step 3 — Get your Apify token

1. https://console.apify.com/account/integrations
2. Copy the **Personal API token**

(Note: `agent/secrets/apify_config.json` already has a token committed for local dev. You can reuse that one as `APIFY_TOKEN` if you don't want to rotate.)

---

## Step 4 — Get your Anthropic API key (optional, recommended)

This unlocks judgment-based scoring (Claude Opus reads each JD instead of keyword counting).

1. https://console.anthropic.com/settings/keys → **Create Key**
2. Copy the value starting with `sk-ant-...`

If you skip this, the agent falls back to heuristic scoring (still works, just lower fidelity).

---

## Step 5 — Add all secrets to GitHub

1. https://github.com/Abhillashjadhav/Dreamjob-agent/settings/secrets/actions
2. Click **New repository secret** for each row below:

| Secret name | Value |
|---|---|
| `APIFY_TOKEN` | from Step 3 |
| `CLAUDE_CODE_OAUTH_TOKEN` | from Step 5.6 (preferred — uses Max plan, $0 incremental) |
| `ANTHROPIC_API_KEY` | from Step 4 (legacy paid fallback — only used if OAuth absent) |
| `GMAIL_CLIENT_ID` | from Step 1.4 (`xxx.apps.googleusercontent.com`) |
| `GMAIL_CLIENT_SECRET` | from Step 1.4 (`GOCSPX-yyy`) |
| `GMAIL_REFRESH_TOKEN` | from Step 2.3 (starts with `1//`) |
| `GMAIL_TO` | `abhilashjadhav@gmail.com` |
| `GDRIVE_CLIENT_ID` | same as `GMAIL_CLIENT_ID` |
| `GDRIVE_CLIENT_SECRET` | same as `GMAIL_CLIENT_SECRET` |
| `GDRIVE_REFRESH_TOKEN` | same as `GMAIL_REFRESH_TOKEN` |
| `GDRIVE_PARENT_FOLDER_ID` | from Step 2.4 |

---

## Step 5.6 — Wire Claude Max plan OAuth for judgment-based scoring (one-time, ~2 min, $0)

The pipeline scores each role with a 6-dimension rubric. Two paths:

- **Heuristic** (current default if no creds): keyword match on title + JD body. Lower-fidelity — the same role can score 70 just for having "platform" in the title.
- **Claude judgment** (preferred): the agent shells out to the `claude` CLI which reads each JD and applies the rubric like a recruiter would. **Uses your existing Claude Max $200/mo plan via OAuth — no incremental cost.**

To enable the Claude judgment path:

1. On your local machine, with Claude Code installed, run:
   ```bash
   claude setup-token
   ```
2. Follow the prompts to authenticate with your Claude account (the same login you use for the Max plan). A long token will be printed to stdout — starts with `sk-ant-oat01-`.
3. Go to https://github.com/Abhillashjadhav/Dreamjob-agent/settings/secrets/actions
4. Click **New repository secret**:
   - **Name:** `CLAUDE_CODE_OAUTH_TOKEN`
   - **Value:** paste the token from Step 2
   - Click **Add secret**

That's it. Tomorrow's run will:
- Use `claude` CLI to score every survivor (consumes Max quota, not API billing)
- Use `claude` CLI's WebFetch to pull real JD bodies for Gmail-sourced roles (currently title-only)
- Emit `scored_via: claude_cli` and `jd_source: actual` per role in the brief

If `CLAUDE_CODE_OAUTH_TOKEN` is absent, the pipeline falls back to heuristic and surfaces `[heuristic-only]` in the brief's subject line so you know which days were degraded.

---

## Step 5.5 — Drop in your LinkedIn connections (for the referral lookup)

The brief shows "no referral path identified" for every fit until you commit your LinkedIn connections export. After you do this once, every role in tomorrow's brief automatically lists any 1st-degree connections you have at that company (with their LinkedIn URL), so you can DM them for a referral before applying.

1. LinkedIn → **Me** (top-right) → **Settings & Privacy** → **Data Privacy** → **Get a copy of your data**
2. Tick **Connections** only → **Request archive**. The download arrives in your email within ~10 min.
3. Unzip; locate `Connections.csv` (~5–10 MB if you have a few thousand connections).
4. Save it to this repo at `data/linkedin_connections.csv` and commit:
   ```bash
   mkdir -p data
   cp ~/Downloads/Connections.csv data/linkedin_connections.csv
   git add data/linkedin_connections.csv
   git commit -m "Add LinkedIn connections export for referral lookup"
   git push
   ```
5. Re-export every ~2 months to keep referrals current. The file stays in your private repo only — it's never sent anywhere external.

If you skip this step, the pipeline still runs end-to-end; the referral line just says "no LinkedIn connections export in repo" and you apply cold.

---

## Step 6 — Test the workflow manually

1. https://github.com/Abhillashjadhav/Dreamjob-agent/actions
2. Click **Daily Job Search Pipeline** in the left sidebar
3. Click **Run workflow** button (right side) → leave inputs blank → **Run workflow**
4. Watch it run. Should complete in 5–10 minutes.

### Expected outcome

- New branch `claude/daily-runs/{today's date}` pushed with `outputs/{date}/` directory
- Drive folder `Dream job Agent / {today's date}` populated with `brief.md` + tailored PDFs
- Gmail draft in your Drafts folder with subject `Job brief — {date} — N fits, M bumped fits...`

If anything fails, the **Actions tab logs** show exactly which step blew up. Common first-run issues are listed below.

---

## Common first-run issues

| Symptom | Cause | Fix |
|---|---|---|
| `403 invalid_grant` from Gmail/Drive | Refresh token expired (60-day limit when app is in test mode) | Either publish the OAuth app (Step 1.3 last bullet), or re-mint the refresh token via Step 2 |
| `401 invalid_client` | Wrong client_id/secret pasted into secrets | Re-paste, ensure no leading/trailing whitespace |
| `Apify 401` | `APIFY_TOKEN` wrong | Check https://console.apify.com/account/integrations |
| `0 raw rows` | Apify ran but got no results (LinkedIn rate-limited the actor) | Re-run the workflow; transient |
| `ANTHROPIC_API_KEY not set` warning | Optional secret not configured | Either add the secret or accept heuristic scoring |
| Drive upload fails on attachment > 5MB | Multipart upload limit | Already handled — PDFs are <100KB |

---

## Step 7 — Set the schedule (already done)

The workflow is already scheduled for `0 3 * * *` (03:00 UTC daily) in `.github/workflows/daily-job-search.yml`. It will fire every morning automatically once Step 6 succeeds once.

To change the time, edit the cron expression. For 04:30 IST (23:00 UTC previous day), use `0 23 * * *`.

---

## What the workflow does each day

```
03:00 UTC  GitHub Actions runs the workflow
03:00:30   Read Gmail JobAlerts/LinkedIn label (last 3 days)
            → extract canonical LinkedIn job URLs (https://www.linkedin.com/jobs/view/{id})
            → typically 30-60 unique URLs/day
03:01      Apify URL-targeted scrape: full JD per Gmail-discovered URL
03:03      Apify query-based scrape: 10 broad title queries (catches breadth)
03:05      Aggregate, dedupe by URL → ~100-200 unique rows with full JDs
03:06      rule_filter.py → drops 80% (title/location/decline list/seen-index)
03:07      scorer.py → judgment scoring per JD (Claude API or heuristic)
03:08-12   resume_pipeline.py → tailored compact PDF per fit (full JD context
            → keyword-bolding matches THE specific role, not generic)
03:13      brief.md + _scored_candidates.json written
03:14      git commit + push to claude/daily-runs/{date}
03:15      Drive upload → Dream job Agent / {date} / *.pdf, brief.md
03:16      Gmail draft → your inbox: subject "Job brief — {date} — N fits..."
            body has every role with apply link + tailored PDF attached
03:17      Done. You wake up, open the draft, blindly click + attach + submit.
```

---

## How to update / extend

- **Change Apify queries:** edit `agent/sources/apify_linkedin.py:LINKEDIN_QUERIES`
- **Change scoring rubric:** edit `agent/scorer.py`
- **Change resume formatting:** edit `agent/resume_pipeline.py`
- **Disable for a day:** go to Actions tab, **Disable workflow** button on the right
- **Run for a backfill date:** Actions → Run workflow → enter `date: 2026-05-12`

---

## Cost

| Service | Monthly cost at daily run cadence |
|---|---|
| GitHub Actions | $0 (private repo gets 2000 free min/month; this run uses ~10 min/day = 300 min/month) |
| Apify `valig/linkedin-jobs-scraper` | ~$5 (residential proxy, 500 rows/day) |
| Anthropic Claude API (optional) | ~$1.50 (each scoring call ~600 tokens × ~30 candidates × $15/1M tokens) |
| Google Workspace APIs | $0 (under quota) |
| **Total** | **~$5–7/month** |

---

## Done

After completing Steps 1–6, you never copy-paste an Apify file again. The pipeline runs autonomously every morning.
