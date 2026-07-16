"""Decline-list enforcement at resume-generation time.

profile/master_profile.json -> decline_list_companies is a hard ban applied
at company level, including sister entities, matched case-insensitively by
substring on the company name (CLAUDE.md hard rule 3). rule_filter.py drops
declined companies at the filter stage; this module is the second, LOUD
enforcement point: at resume generation a declined company is refused with a
<jd_id>.DECLINED.md sidecar so the refusal is visible on the daily-runs
branch, not silent.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PROFILE_PATH = ROOT / "profile" / "master_profile.json"


def load_decline_list(path: Path = _PROFILE_PATH) -> list[str]:
    """Return decline_list_companies from the canonical profile."""
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("decline_list_companies", [])


def declined_match(company: str,
                   decline_list: list[str] | None = None) -> str | None:
    """Return the decline-list entry that matches `company`, else None.

    Case-insensitive substring match on the company name — identical to
    rule_filter.py, so sister entities ("Amazon Web Services" matches
    "Amazon", "VistaCreate" matches "Vista") all hit.
    """
    decline_list = decline_list if decline_list is not None else load_decline_list()
    company_lower = (company or "").lower()
    if not company_lower:
        return None
    for declined in decline_list:
        if declined.lower() in company_lower:
            return declined
    return None


def write_declined_sidecar(out_dir: Path, jd_id: str, company: str,
                           matched: str, title: str = "") -> Path:
    """Write <jd_id>.DECLINED.md and return its path.

    Called instead of generating a resume when a JD's company is on the
    decline list. The sidecar names the matched entry so the refusal is
    auditable.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"{jd_id}.DECLINED.md"
    content = (
        f"# RESUME DECLINED — company on the decline list\n\n"
        f"- **Timestamp (UTC):** {datetime.now(timezone.utc).isoformat()}\n"
        f"- **Company:** {company}\n"
        f"- **Role:** {title or '(unspecified)'}\n"
        f"- **Decline-list entry matched:** `{matched}`\n\n"
        f"`{company}` matched the decline-list entry `{matched}` "
        f"(case-insensitive substring — covers sister entities). Per CLAUDE.md "
        f"hard rule 3 the decline list is a hard ban at company level. "
        f"**No resume was generated** for this role and it is excluded from "
        f"the brief.\n\n"
        f"The decline list lives in `profile/master_profile.json` -> "
        f"`decline_list_companies`. If this match is wrong, correct the list "
        f"there.\n"
    )
    sidecar.write_text(content)
    return sidecar
