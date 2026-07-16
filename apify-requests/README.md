# Apify on-demand bridge

A GitHub Actions workflow that lets Claude (or anyone) request LinkedIn job
data from Apify by committing a JSON request file. Apify runs on GitHub's
network (where `api.apify.com` is reachable, unlike Claude Code's sandbox)
and commits the result back to the branch.

## Usage

1. **Create a request file** at `apify-requests/<id>.json`:

   ```json
   {
     "id": "2026-05-25-director-pm",
     "title": "Director Product Manager",
     "location": "Bengaluru",
     "datePosted": "r604800",
     "experienceLevel": ["4", "5"],
     "limit": 30
   }
   ```

2. **Push it** to `main` (or any branch with the workflow). The workflow
   fires, runs `scripts/apify_bridge.py`, calls Apify, and commits
   `apify-results/<id>.json` back to the same branch.

3. **Pull the result** (`git pull`) and read `apify-results/<id>.json` —
   contains the full Apify response including JD bodies.

## Request schema

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Unique identifier; result file is named the same. |
| `title` | yes | — | One job title (Apify limitation: one title per call). |
| `location` | no | `"India"` | City or country. |
| `datePosted` | no | `"r604800"` (7d) | `r604800`=7d, `r2592000`=30d. |
| `experienceLevel` | no | `["4","5"]` | 4=director, 5=executive. |
| `contractType` | no | `["F"]` | F=full-time. |
| `limit` | no | `30` | Max items returned. |
| `companyName` | no | — | Optional company filter (array). |

## Idempotency

If `apify-results/<id>.json` already exists, the request is skipped. To
re-run, delete the result file first.

## Cost

Apify pricing: ~$0.40 per 1,000 results. A typical 30-item request ≈ $0.012.
Token is read from the `APIFY_TOKEN` repo secret (already configured for
the daily cron); falls back to `agent/secrets/apify_config.json` if absent.

## Why this exists

Claude Code's sandbox blocks `api.apify.com` with `Host not in allowlist`
(HTTP 403). The daily cron in `.github/workflows/daily-job-search.yml` runs
on GitHub's network where Apify is reachable, so this bridge lets Claude
get the same data on-demand instead of waiting for the daily 03:00 UTC run.
