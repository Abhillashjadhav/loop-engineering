"""Gmail-only fallback scorer.

When `apify_fallback_mode == 'gmail_only'`, Apify is skipped and the
candidate pool is whatever the Gmail alerts (+ Greenhouse) produced.
Gmail-sourced rows carry title + company + location parsed from the alert
email but NO JD body. This module scores that reduced signal honestly.

Two adjustments vs the normal scorer, both surfaced in the output:

  1. `reduced_confidence: True` on every candidate — the brief flags the
     whole run as lower-fidelity so the user knows scores are title-only.

  2. A lowered fit threshold. Title-only scoring systematically
     under-scores the domain / tech rubric dimensions (there is no JD text
     to keyword-match against), so a strict 70 gate would discard genuine
     fits that merely lack JD text. The threshold drops by 10.

CONSTRAINT COMPLIANCE: this module does NOT modify `scorer.py` or
`rule_filter.py`. It imports `scorer.heuristic_score` read-only and
post-processes the result — the scoring rubric itself is untouched.

Adaptation: spec path was `pipeline/gmail_only_scorer.py`; placed at
`agent/gmail_only_scorer.py` for import consistency.
"""
from __future__ import annotations

from agent import scorer

# Title-only scoring under-reads domain/tech by ~10 points on average
# (no JD body to match keywords). Drop both gates by 10 to compensate.
GMAIL_ONLY_FIT_THRESHOLD = scorer.FIT_THRESHOLD - 10        # 80 -> 70
GMAIL_ONLY_NEAR_MISS_FLOOR = scorer.NEAR_MISS_FLOOR - 10    # 60 -> 50


def score_gmail_only(candidates: list[dict], profile: dict) -> list[dict]:
    """Score Gmail-sourced candidates on title+company with reduced confidence.

    Returns the same dict shape as `scorer.score_candidates` so the rest of
    the pipeline (brief, drift, invariants) is unchanged — plus the extra
    keys `reduced_confidence`, `confidence_note`, and `scored_via`.
    """
    out: list[dict] = []
    for c in candidates:
        s = scorer.heuristic_score(c)  # read-only use of the public rubric
        total = int(s.get("score", 0))
        bumped = int(s.get("bumped_score", total) or total)
        eff = max(total, bumped)

        # Re-derive disposition against the lowered gthresholds.
        if eff >= GMAIL_ONLY_FIT_THRESHOLD:
            disp = "fit" if total >= GMAIL_ONLY_FIT_THRESHOLD else "bumped_fit"
        elif eff >= GMAIL_ONLY_NEAR_MISS_FLOOR:
            disp = "near_miss"
        else:
            disp = "silent_drop"

        s["disposition"] = disp
        s["reduced_confidence"] = True
        s["scored_via"] = "gmail_only_fallback"
        s["jd_source"] = s.get("jd_source", "title_only")
        s["confidence_note"] = (
            "Apify skipped (apify_fallback_mode=gmail_only). Scored on "
            "title+company only — no JD body. Fit threshold lowered "
            f"{scorer.FIT_THRESHOLD} -> {GMAIL_ONLY_FIT_THRESHOLD} to "
            "compensate for systematically under-read domain/tech scores. "
            "Verify each JD manually before applying."
        )
        out.append(s)
    return out
