"""Culture lookup — formats Indeed company-data MCP response for the brief.

Web fetch is firewalled in the routine sandbox, so Glassdoor / Levels.fyi /
ATS career pages are unreachable. Indeed MCP exposes the same employee-
review data via `mcp__...__get_company_data`, which IS available, so this
module replaces the previous web-fetch path.

Architecture: same shape as `agent/sources/gmail_linkedin.py`. The MCP
call is agent-side; this module is a pure formatter — the agent passes
in the raw Indeed response and gets back the snapshot dict that the
brief writer renders.

Usage (agent-side):
    raw = mcp__indeed__get_company_data(companyName="Harvey", ...)
    snapshot = format_culture_snapshot(raw, company="Harvey")
    # snapshot["available"] = True/False
    # snapshot["one_liner"] = "Indeed 3.8/5 (31 reviews) — strong culture, weaker comp"
    # snapshot["details"] = {...all rating fields...}
"""
from __future__ import annotations


CULTURE_UNAVAILABLE = {
    "available": False,
    "one_liner": "culture data not available",
    "details": None,
}


def _safe(d: dict | None, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def format_culture_snapshot(indeed_response: dict | None,
                            company: str) -> dict:
    """Reduce Indeed's get_company_data response to a brief-ready snapshot.

    Returns CULTURE_UNAVAILABLE shape when:
      - indeed_response is None or empty
      - the response carries no `ugcStats.ratings_in_1_to_5_scale` block
      - overallRating is missing (means Indeed has the company page but no
        review aggregate, e.g. brand-new listing)

    On success returns:
        {
          "available": True,
          "one_liner": "Indeed {rating}/5 ({reviews} reviews) — {tone}",
          "details": {
              "overall": float,
              "culture": float,
              "work_life_balance": float,
              "management": float,
              "compensation": float,
              "advancement": float,
              "would_recommend_pct": float,   # 0-100
              "ceo_approval_pct": float,      # 0-100
              "review_count": int,
              "for_location": "US"|"IN"|...,
              "company_page_url": str,
              "interview_difficulty": "EASY"|"MEDIUM"|"HARD"|None,
              "interview_process_length": "A_WEEK"|"TWO_WEEKS"|"A_MONTH"|None,
          },
        }
    """
    if not indeed_response:
        return dict(CULTURE_UNAVAILABLE)

    employer = indeed_response.get("employerData", {}) or {}
    ratings = _safe(employer, "ugcStats", "ratings_in_1_to_5_scale", default={}) or {}
    overall = ratings.get("overallRating")
    if overall is None:
        return dict(CULTURE_UNAVAILABLE)

    yes = _safe(employer, "ugcStats", "recommendFriend", "yesCount", default=0) or 0
    no = _safe(employer, "ugcStats", "recommendFriend", "noCount", default=0) or 0
    total_reviews = yes + no
    would_recommend_pct = round(100 * yes / total_reviews, 0) if total_reviews else None

    ceo_pct = _safe(employer, "ugcStats", "ceo_approval_percentage", "approval_percentage")
    ceo_pct = round(ceo_pct * 100, 0) if ceo_pct is not None else None

    details = {
        "overall": overall,
        "culture": ratings.get("cultureAndValuesRating"),
        "work_life_balance": ratings.get("workLifeBalanceRating"),
        "management": ratings.get("managementRating"),
        "compensation": ratings.get("compensationAndBenefitsRating"),
        "advancement": ratings.get("jobSecurityAndAdvancementRating"),
        "would_recommend_pct": would_recommend_pct,
        "ceo_approval_pct": ceo_pct,
        "review_count": total_reviews,
        "for_location": ratings.get("forLocation"),
        "company_page_url": employer.get("companyPageUrl"),
        "interview_difficulty": _safe(employer, "ugcStats", "interview", "difficulty"),
        "interview_process_length": _safe(employer, "ugcStats", "interview", "processLength"),
    }

    one_liner = _build_one_liner(company, details)
    return {"available": True, "one_liner": one_liner, "details": details}


def _build_one_liner(company: str, d: dict) -> str:
    """Build the brief's culture line — fact-only, no fabrication."""
    overall = d["overall"]
    review_count = d["review_count"]
    parts = [f"Indeed {overall}/5"]
    if review_count:
        parts.append(f"({review_count} reviews)")
    rec = d["would_recommend_pct"]
    if rec is not None:
        parts.append(f"— {rec:.0f}% would recommend")
    # One signal call-out — pick the strongest and weakest sub-rating to
    # keep the line useful without faking depth.
    sub = {
        "culture": d["culture"], "WLB": d["work_life_balance"],
        "mgmt": d["management"], "comp": d["compensation"],
        "advancement": d["advancement"],
    }
    rated = [(k, v) for k, v in sub.items() if v is not None]
    if rated:
        rated.sort(key=lambda kv: kv[1])
        weakest = rated[0]
        strongest = rated[-1]
        if strongest[1] != weakest[1]:
            parts.append(f"(strong {strongest[0]} {strongest[1]:.1f}, weak {weakest[0]} {weakest[1]:.1f})")
    return " ".join(parts)


def format_brief_block(snapshot: dict) -> str:
    """Render the snapshot as a markdown line for the brief.

    Renders both the one-liner and a compact details line with all
    ratings, so the user can eyeball culture/WLB/mgmt/comp at a glance
    without losing the headline number.
    """
    if not snapshot.get("available"):
        return "**Culture snapshot:** culture data not available *(Indeed has no aggregated review data for this company — `[partial-culture]` flag)*"

    d = snapshot["details"]

    def _r(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "—"

    detail_bits = [
        f"culture {_r(d['culture'])}",
        f"WLB {_r(d['work_life_balance'])}",
        f"mgmt {_r(d['management'])}",
        f"comp {_r(d['compensation'])}",
        f"advancement {_r(d['advancement'])}",
    ]
    ceo = d.get("ceo_approval_pct")
    if ceo is not None:
        detail_bits.append(f"CEO approval {ceo:.0f}%")
    url = d.get("company_page_url") or ""
    url_bit = f" · [Indeed page]({url})" if url else ""
    return (
        f"**Culture snapshot:** {snapshot['one_liner']}\n"
        f"  · {' · '.join(detail_bits)}{url_bit}"
    )
