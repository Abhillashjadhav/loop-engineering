"""Apify on-demand bridge — fetches LinkedIn job data via Apify and commits
results back to the repo.

Triggered by GitHub Actions on every push to `apify-requests/*.json`.

Per-request lifecycle:
  apify-requests/<id>.json     ← committed by the requester (e.g. Claude via MCP)
  apify-results/<id>.json      ← committed by this script after the Apify call

A request is processed if no result file exists for its `id`. Idempotent —
re-running the workflow on the same commit produces no duplicates.

Request schema (all keys optional except `id`, `title`):
  {
    "id":             "2026-05-25-momentum-search",   # unique
    "title":          "Director Product Manager",      # required
    "location":       "Bengaluru",                     # default "India"
    "datePosted":     "r604800",                       # last 7d default
    "experienceLevel": ["4","5"],                      # 4=director 5=executive
    "limit":          30,                              # default 30
    "companyName":    ["WorkIndia"]                    # optional filter
  }

Result schema:
  {
    "id":           "<same id>",
    "fetched_at":   "<iso>",
    "request":      {...echo of the request...},
    "items":        [ ...raw Apify items, full JD bodies included... ],
    "item_count":   N,
    "error":        null | "<reason>"
  }

The script never raises on a request error — it writes an error result so
the requester can see what happened. A non-zero exit code only fires if no
requests at all could be processed (e.g. missing token), so the workflow
job stays green for normal runs.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urlreq
from urllib import error as urlerr

ROOT = Path(__file__).resolve().parent.parent
REQUESTS_DIR = ROOT / "apify-requests"
RESULTS_DIR = ROOT / "apify-results"

APIFY_ACTOR = "valig~linkedin-jobs-scraper"
APIFY_RUN_URL = (
    f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
)

# Default request shape; user request overrides these keys.
DEFAULTS = {
    "location": "India",
    "datePosted": "r604800",      # past 7 days
    "experienceLevel": ["4", "5"],  # director + executive
    "contractType": ["F"],          # full-time only
    "limit": 30,
}


def call_apify(token: str, payload: dict, timeout: int = 180) -> tuple[list, str | None]:
    """Fire one run-sync call against the actor. Returns (items, error)."""
    url = f"{APIFY_RUN_URL}?token={token}&memory=512&timeout=120"
    body = json.dumps(payload).encode("utf-8")
    req = urlreq.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                items = json.loads(raw)
            except json.JSONDecodeError as e:
                return [], f"non-JSON response: {e}"
            if not isinstance(items, list):
                return [], f"unexpected response shape: {type(items).__name__}"
            return items, None
    except urlerr.HTTPError as e:
        return [], f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
    except urlerr.URLError as e:
        return [], f"URLError: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"


def build_payload(req_data: dict) -> dict:
    """Merge request with defaults; drop our internal `id` key."""
    out = {**DEFAULTS}
    for k, v in req_data.items():
        if k == "id":
            continue
        if v is not None:
            out[k] = v
    if "title" not in out:
        raise ValueError("request missing required `title` field")
    return out


def process_one(req_path: Path, token: str) -> Path | None:
    """Process a single request file. Returns the result path or None."""
    req_data = json.loads(req_path.read_text())
    req_id = req_data.get("id") or req_path.stem
    result_path = RESULTS_DIR / f"{req_id}.json"
    if result_path.exists():
        print(f"  [{req_id}] already has result — skipping")
        return None
    try:
        payload = build_payload(req_data)
    except ValueError as ve:
        result = {
            "id": req_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "request": req_data,
            "items": [],
            "item_count": 0,
            "error": str(ve),
        }
    else:
        t0 = time.time()
        items, err = call_apify(token, payload)
        result = {
            "id": req_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "request": req_data,
            "payload_sent": payload,
            "items": items,
            "item_count": len(items),
            "elapsed_s": round(time.time() - t0, 1),
            "error": err,
        }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    status = f"err={result['error']!r}" if result.get("error") else f"items={result['item_count']}"
    print(f"  [{req_id}] {status}")
    return result_path


def main() -> int:
    token = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not token:
        # Fallback to checked-in config (matches agent/sources/apify_linkedin.py)
        cfg_path = ROOT / "agent" / "secrets" / "apify_config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            tok = (cfg.get("apify_token") or "").strip()
            if tok and not tok.startswith("REPLACE_"):
                token = tok
    if not token:
        print("ERROR: APIFY_TOKEN missing — set it as a repo secret or in "
              "agent/secrets/apify_config.json", file=sys.stderr)
        return 1

    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    requests_in = sorted(REQUESTS_DIR.glob("*.json"))
    if not requests_in:
        print("No requests in apify-requests/ — nothing to do")
        return 0

    print(f"Processing {len(requests_in)} request file(s):")
    n_new = 0
    for req in requests_in:
        out = process_one(req, token)
        if out is not None:
            n_new += 1
    print(f"\nWrote {n_new} new result file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
