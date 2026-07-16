"""JD enrichment via the `claude` CLI.

Why this module exists: roles harvested from Gmail LinkedIn alerts arrive with
title + company + location + URL, but NO JD body — the alert email only quotes
the role card, not the description. The scorer's domain/tech dimensions degrade
to title-only without it.

This module asks Claude (running under the user's Max plan via OAuth, so $0
extra) to fetch the LinkedIn job page and return a structured summary. If the
fetch fails (LinkedIn blocks the IP, page expired, etc.) we mark the candidate
with `jd_source: "title_only"` and DO NOT fabricate JD content — the scorer
will reflect the reduced signal honestly in the brief.

Honesty contract:
    jd_source = "actual"     → JD body came from the live page
    jd_source = "title_only" → enrichment failed; scorer sees title+company only

Usage (programmatic):
    from agent.jd_enrich import enrich_candidates
    enriched = enrich_candidates(filtered_candidates, react_logger=log_fn)

Env:
    CLAUDE_CODE_OAUTH_TOKEN — required for the CLI to authenticate against the
                              user's Max plan. If absent, every candidate is
                              returned unchanged with jd_source unset (the
                              heuristic scorer will then mark it title_only).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Callable


_FETCH_PROMPT = (
    'Fetch the LinkedIn job page at {url} and return ONLY a JSON object with '
    'keys "title", "company", "location", "description_excerpt" '
    '(2000-3000 chars of the JD body, plain text, no HTML). If the page is '
    'unreachable, blocked, or expired, return {{"error": "<short reason>"}}. '
    'Do not invent content; if you cannot read the page, return the error form.'
)


def _has_cli() -> bool:
    return (shutil.which("claude") is not None
            and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip() != "")


def fetch_one_jd(url: str, timeout: int = 90) -> dict:
    """Call `claude -p` with WebFetch enabled and parse the JSON envelope.

    Returns either {"description_excerpt": "...", ...} on success or
    {"error": "..."} on failure. Never raises.
    """
    if not url or not _has_cli():
        return {"error": "no-cli-or-url"}
    prompt = _FETCH_PROMPT.format(url=url)
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--model", "claude-opus-4-7",
             "--output-format", "json",
             "--max-turns", "3",
             "--allowed-tools", "WebFetch"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ},
        )
        if proc.returncode != 0:
            return {"error": f"rc={proc.returncode} stderr={proc.stderr[-200:]}"}
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result") or ""
        m = re.search(r'\{[\s\S]*\}', result_text)
        if not m:
            return {"error": "no-json-in-response"}
        payload = json.loads(m.group())
        if "error" in payload:
            return {"error": payload["error"]}
        if not (payload.get("description_excerpt") or "").strip():
            return {"error": "empty-description"}
        return payload
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def enrich_candidates(candidates: list[dict],
                      react_logger: Callable[[dict], None] | None = None,
                      only_missing: bool = True) -> list[dict]:
    """Fill in `description_excerpt` for candidates that lack one.

    `only_missing=True` (default): we only call WebFetch for candidates whose
    description_excerpt is empty or shorter than 200 chars — typical of Gmail-
    sourced rows. Apify/Greenhouse rows arrive with rich JDs and are skipped.

    Every candidate ends with a stable `jd_source` field: "actual" if we have
    real JD text (either pre-existing or freshly fetched), "title_only" otherwise.
    Honesty rule: we never overwrite existing JD content with fabricated text.
    """
    out: list[dict] = []
    cli_available = _has_cli()
    for c in candidates:
        existing = (c.get("description_excerpt") or "").strip()
        needs_fetch = only_missing and len(existing) < 200
        if not needs_fetch:
            c2 = dict(c)
            c2.setdefault("jd_source", "actual" if existing else "title_only")
            out.append(c2)
            continue
        if not cli_available:
            c2 = dict(c)
            c2.setdefault("jd_source", "title_only")
            if react_logger:
                react_logger({"step": "2b-jd-enrich",
                              "company": c.get("company"),
                              "decision": "skip-no-cli",
                              "jd_source": "title_only"})
            out.append(c2)
            continue
        url = c.get("url") or c.get("apply_url") or ""
        if react_logger:
            react_logger({"step": "2b-jd-enrich",
                          "company": c.get("company"),
                          "intent": "fetch JD via claude CLI",
                          "url": url})
        result = fetch_one_jd(url)
        c2 = dict(c)
        if "error" in result:
            c2["jd_source"] = "title_only"
            c2["jd_fetch_error"] = result["error"]
            if react_logger:
                react_logger({"step": "2b-jd-enrich",
                              "company": c.get("company"),
                              "observation": result["error"],
                              "decision": "title_only"})
        else:
            c2["description_excerpt"] = (result.get("description_excerpt") or "")[:3000]
            c2["jd_source"] = "actual"
            if react_logger:
                react_logger({"step": "2b-jd-enrich",
                              "company": c.get("company"),
                              "observation": f"fetched {len(c2['description_excerpt'])} chars",
                              "decision": "actual"})
        out.append(c2)
    return out
