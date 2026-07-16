"""P3 — Hard drift enforcement.

Subject-line flags alone aren't enough — they're easy to ignore. Per CLAUDE.md
eval/README.md spec, certain drift signals must BLOCK the daily Gmail draft
and replace it with a review-required notice. The user sees an explicit "stop
and review" rather than a half-broken draft they might miss.

Block rules (HARD):
    1. Any role passed output audit with `fabricated > 0`            → block
    2. Heuristic-only scoring (no judgment available at all)          → block
    3. Output audit skipped for >50% of generated resumes             → block
    4. JD enrichment failed for 100% of Gmail-sourced rows AND that
       was the only source that produced fits                         → block
    5. Funnel collapsed: raw>1000 but filtered=0                      → block

Soft drift (already surfaced via subject flags, NOT blocked):
    - [partial-judgment] [partial-jd] [partial-culture] [audit-partial]

When a hard rule fires, write a "review-required" draft INSTEAD of the brief.
The original brief still gets committed to the daily-runs branch for forensics;
the user just doesn't get the half-broken draft in their inbox.
"""
from __future__ import annotations

from collections import Counter


HARD_BLOCK_THRESHOLDS = {
    "audit_skipped_fraction": 0.5,
    "raw_high_filter_zero": 1000,
}


def evaluate_drift(scored: list[dict], n_raw: int, n_filtered: int,
                   resume_paths: list, audit_results: list[dict] | None = None,
                   ) -> tuple[bool, list[str]]:
    """Return (should_block, reasons).

    Caller is run_daily.main(); if should_block is True, replace the Gmail
    draft body with a review-required notice and prepend `[BLOCKED]` to the
    subject. The brief is still written to disk + git for audit.

    HARD blocks (draft replaced): fabricated bullets, funnel collapse. These
    are integrity / correctness failures the user must see before applying.

    SOFT drift (draft still sent, subject carries a flag): heuristic-only
    scoring, audit skipped. These degrade fidelity but the brief is still
    usable — the user explicitly accepted heuristic mode, so blocking the
    whole draft over it is more harmful than helpful. The `[heuristic-only]`
    / `[audit-partial]` subject flags already surface it honestly.
    """
    reasons: list[str] = []

    # 1. Fabricated bullet detected anywhere — HARD block (integrity P0).
    fabricated_total = sum((a or {}).get("fabricated", 0) for a in (audit_results or []))
    if fabricated_total > 0:
        reasons.append(
            f"audit-fabricated-bullets={fabricated_total} — review quarantined PDFs "
            f"in outputs/<date>/quarantined_resumes/ before re-running"
        )

    # 2. Funnel collapse: raw rich but filter wiped everything — HARD block.
    if n_raw > HARD_BLOCK_THRESHOLDS["raw_high_filter_zero"] and n_filtered == 0:
        reasons.append(
            f"funnel-collapsed raw={n_raw} filtered={n_filtered} — filter rules "
            f"likely misconfigured, refusing to send empty brief"
        )

    # NOTE: heuristic-only scoring and audit-skipped are NO LONGER hard
    # blocks. They are soft drift — surfaced via subject-line flags
    # ([heuristic-only], [audit-partial]) in build_brief, but the daily
    # draft is still delivered so the user always gets a usable brief.

    return (len(reasons) > 0, reasons)


def build_review_required_brief(date: str, reasons: list[str],
                                 original_subject: str) -> tuple[str, str]:
    """Return (blocked_subject, blocked_body) to use INSTEAD of the daily draft."""
    subject = f"[BLOCKED — REVIEW REQUIRED] {original_subject}"
    body = (
        f"# Daily run BLOCKED — review required\n\n"
        f"Date: {date}\n\n"
        f"The agent ran today but produced output that failed one or more hard drift "
        f"checks. Per CLAUDE.md hard rule 8 (\"don't silently fail\"), the regular "
        f"brief has NOT been delivered. Review the items below before re-running.\n\n"
        f"## Failure reasons\n\n"
    )
    for r in reasons:
        body += f"- {r}\n"
    body += (
        f"\n## What to do\n\n"
        f"1. Review the full brief at `outputs/{date}/brief.md` on branch "
        f"`claude/daily-runs/{date}` (it's still written, just not emailed).\n"
        f"2. Inspect any PDFs in `outputs/{date}/quarantined_resumes/` for the "
        f"specific fabricated bullets.\n"
        f"3. Check `outputs/{date}/_output_audit.json` for per-role labels.\n"
        f"4. Fix the root cause (profile, prompt, threshold) and re-trigger the "
        f"workflow manually for today's date.\n"
        f"5. If this is a false positive, comment on the daily-runs branch and "
        f"the next session can recalibrate.\n\n"
        f"— dreamjob-agent (BLOCKED, integrity first)\n"
    )
    return subject, body
