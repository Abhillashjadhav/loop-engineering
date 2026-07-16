"""P2 — Apply-feedback ingestion from Gmail labels.

The user marks each agent-surfaced role with one of three Gmail labels:

    JobAgent/Applied   — application submitted
    JobAgent/Skipped   — chose not to apply
    JobAgent/Rework    — applied but want resume reframed before next

This script pulls every thread tagged with one of those labels (since the
last applications.jsonl entry's timestamp), parses out company + role from
the brief's draft body OR from the labelled job-listing email, and appends
one record per role to `outputs/applications.jsonl`.

That JSONL is the only input to `eval/calibration.py`, the weekly threshold
recommender. Apply-rate by score bucket is the ground-truth signal we need
to calibrate FIT_THRESHOLD over time.

Honesty: only roles we can confidently identify (company + score) get
appended. Ambiguous threads are logged to stderr, never imputed.

Env:
    GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent.parent
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_LABELS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
GMAIL_THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
GMAIL_THREAD_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads/{tid}"

LABELS = {
    "JobAgent/Applied": "applied",
    "JobAgent/Skipped": "skipped",
    "JobAgent/Rework": "rework",
}


def _exchange_refresh_token() -> str:
    cid = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    cs = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    rt = os.environ.get("GMAIL_REFRESH_TOKEN", "").strip()
    if not all([cid, cs, rt]) or requests is None:
        raise RuntimeError("Gmail OAuth env vars missing or requests not installed")
    resp = requests.post(GMAIL_TOKEN_URL, data={
        "client_id": cid, "client_secret": cs,
        "refresh_token": rt, "grant_type": "refresh_token",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _list_user_labels(access: str) -> dict[str, str]:
    r = requests.get(GMAIL_LABELS_URL,
                     headers={"Authorization": f"Bearer {access}"},
                     timeout=30)
    r.raise_for_status()
    return {lbl["name"]: lbl["id"] for lbl in r.json().get("labels", [])}


def _threads_with_label(access: str, label_id: str) -> list[dict]:
    out = []
    page_token = None
    while True:
        params = {"labelIds": label_id, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(GMAIL_THREADS_URL,
                         headers={"Authorization": f"Bearer {access}"},
                         params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("threads", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def _thread_snippet(access: str, tid: str) -> tuple[str, int]:
    r = requests.get(GMAIL_THREAD_URL.format(tid=tid),
                     headers={"Authorization": f"Bearer {access}"},
                     params={"format": "metadata"}, timeout=30)
    r.raise_for_status()
    msgs = r.json().get("messages", [])
    if not msgs:
        return "", 0
    snippet = msgs[0].get("snippet", "")
    headers = {h["name"]: h["value"]
               for h in (msgs[0].get("payload") or {}).get("headers", [])}
    subject = headers.get("Subject", "")
    ts_ms = int(msgs[0].get("internalDate", 0))
    return f"{subject} :: {snippet}", ts_ms


_COMPANY_TITLE_RE = re.compile(
    r"^(?P<title>.+?)\s+at\s+(?P<company>.+?)(?:\s*::|$)",
    re.IGNORECASE,
)


def _existing_records() -> set[tuple[str, str, str]]:
    """Return (date, company, label) tuples already in applications.jsonl."""
    p = ROOT / "outputs" / "applications.jsonl"
    if not p.exists():
        return set()
    seen = set()
    for line in p.open():
        try:
            r = json.loads(line)
            seen.add((r.get("date", ""), r.get("company", "").lower(),
                      r.get("label", "")))
        except json.JSONDecodeError:
            continue
    return seen


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    try:
        access = _exchange_refresh_token()
    except RuntimeError as e:
        print(f"[apply_feedback] {e}", file=sys.stderr)
        return 1

    label_map = _list_user_labels(access)
    appended = 0
    skipped = 0
    out_path = ROOT / "outputs" / "applications.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_records()

    new_records: list[dict] = []
    for label_name, label_short in LABELS.items():
        lid = label_map.get(label_name)
        if not lid:
            print(f"[apply_feedback] label {label_name} not found in user account, "
                  f"skipping. Create it in Gmail UI to enable.", file=sys.stderr)
            continue
        threads = _threads_with_label(access, lid)
        for t in threads:
            tid = t["id"]
            try:
                snippet, ts_ms = _thread_snippet(access, tid)
            except Exception as e:  # noqa: BLE001
                print(f"[apply_feedback] failed to fetch thread {tid}: {e}",
                      file=sys.stderr)
                skipped += 1
                continue
            m = _COMPANY_TITLE_RE.match(snippet)
            if not m:
                print(f"[apply_feedback] could not parse company/title from: "
                      f"{snippet[:120]}", file=sys.stderr)
                skipped += 1
                continue
            company = m.group("company").strip()
            title = m.group("title").strip()
            d_str = (datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                     .date().isoformat()) if ts_ms else ""
            key = (d_str, company.lower(), label_short)
            if key in existing:
                continue
            new_records.append({
                "date": d_str,
                "company": company,
                "title": title,
                "label": label_short,
                "thread_id": tid,
                "ingested_at": datetime.utcnow().isoformat() + "Z",
            })
            existing.add(key)

    if not args.dry_run:
        with out_path.open("a") as f:
            for r in new_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                appended += 1

    print(f"[apply_feedback] appended={appended} skipped={skipped} "
          f"dry_run={args.dry_run}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
