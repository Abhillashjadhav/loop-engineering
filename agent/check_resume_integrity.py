"""Resume integrity validator — programmatic enforcement of the standing rules
that have been repeated by hand too many times.

Run it before generating, rendering, or sharing ANY resume:

    python agent/check_resume_integrity.py            # checks master_profile (post-patch)
    python agent/check_resume_integrity.py --draft x.json   # checks an LLM draft

Exit code 0 = clean, 1 = violation(s). The `resume-integrity` skill calls this
as a hard gate. Rules encoded here come from CLAUDE.md hard rules + the
master_profile.json constraints + lessons logged in this repo's sessions.

The single most-repeated mistake: appending "Product" to PRE-AMAZON titles
(Flipkart/IndiaMart/LeEco/etc.). That class of bug is checked at Layer 1 below
against the *patched* profile — i.e. exactly the titles the renderer will emit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

# Pull the canonical rule constants from the pipeline so there is ONE source of
# truth. Fall back to literals if the import path changes.
try:
    import resume_pipeline as rp  # type: ignore
    PRE_AMAZON_COMPANIES = set(rp.PRE_AMAZON_COMPANIES)
    _patch = rp.patch_profile_for_skill_md
except Exception:  # pragma: no cover
    PRE_AMAZON_COMPANIES = {
        "PayTM", "IndiaMart", "LeEco", "Flipkart",
        "Marico Industries", "AgroTech Foods Ltd",
    }
    _patch = None

# Exact-title hard rules (CLAUDE.md §5 + master_profile constraints).
EXACT_TITLES = {
    "PayTM": "AVP",
    "RADAR by AIMleap": "Product Advisor (Pro Bono)",
}

# Pre-Amazon literal titles (the verbatim, non-embellished values).
PRE_AMAZON_TITLES = {
    "PayTM": "AVP",
    "IndiaMart": "Vice President",
    "LeEco": "Senior Manager",
    "Flipkart": "Senior Manager",
    "Marico Industries": "Area Sales Manager",
    "AgroTech Foods Ltd": "Area Sales Manager",
}

# Companies/strings that must never appear in any resume artifact.
FORBIDDEN_STRINGS = {"MJ Internet Pvt Ltd"}

_PRODUCT_RE = re.compile(r"\bproduct\b", re.IGNORECASE)


def check_experience(experience: list[dict]) -> list[str]:
    """Return a list of violation strings for an experience list (each a
    {company, title} dict)."""
    violations: list[str] = []
    for role in experience:
        co = (role.get("company") or "").strip()
        title = (role.get("title") or "").strip()
        # Rule 1: pre-Amazon titles never carry "Product".
        if co in PRE_AMAZON_COMPANIES and _PRODUCT_RE.search(title):
            violations.append(
                f"PRE-AMAZON TITLE has 'Product': {co} -> {title!r} "
                f"(should be {PRE_AMAZON_TITLES.get(co, 'the literal title')!r})")
        # Rule 2: exact-title hard rules.
        if co in EXACT_TITLES and title != EXACT_TITLES[co]:
            violations.append(
                f"EXACT-TITLE mismatch: {co} -> {title!r} "
                f"(must be {EXACT_TITLES[co]!r})")
        # Rule 3: forbidden company name.
        for bad in FORBIDDEN_STRINGS:
            if bad.lower() in co.lower() or bad.lower() in title.lower():
                violations.append(f"FORBIDDEN string in role: {bad!r} ({co})")
    return violations


def check_forbidden_blob(text: str) -> list[str]:
    return [f"FORBIDDEN string present: {b!r}"
            for b in FORBIDDEN_STRINGS if b.lower() in (text or "").lower()]


def validate_profile(path: Path) -> tuple[bool, list[str]]:
    """Validate master_profile AFTER applying the render-time patch — i.e. the
    exact titles the PDF will show. The forbidden-string scan covers only the
    rendered content (experience company/title/achievements), NOT the
    constraints block — which legitimately *names* forbidden companies."""
    profile = json.loads(path.read_text())
    patched = _patch(profile) if _patch else profile
    experience = patched.get("experience", [])
    v = check_experience(experience)
    # Build a content blob from experience only (companies, titles, bullets).
    parts: list[str] = []
    for role in experience:
        parts.append(role.get("company", ""))
        parts.append(role.get("title", ""))
        ach = role.get("achievements") or role.get("bullets") or []
        parts.extend(str(a) for a in ach)
    v += check_forbidden_blob(" ".join(parts))
    return (not v), v


def validate_draft(draft: dict) -> tuple[bool, list[str]]:
    """Validate an LLM resume draft ({roles:[{company,title,bullets}]})."""
    roles = draft.get("roles", [])
    v = check_experience(roles)
    v += check_forbidden_blob(json.dumps(draft, ensure_ascii=False))
    return (not v), v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=str(ROOT / "profile" / "master_profile.json"))
    ap.add_argument("--draft", help="Path to an LLM draft JSON to validate instead")
    args = ap.parse_args()

    if args.draft:
        ok, v = validate_draft(json.loads(Path(args.draft).read_text()))
        target = args.draft
    else:
        ok, v = validate_profile(Path(args.profile))
        target = args.profile

    if ok:
        print(f"✅ resume integrity OK — {target}")
        return 0
    print(f"❌ resume integrity FAILED — {target}")
    for line in v:
        print(f"   - {line}")
    print("\nFix the source (TITLE_OVERRIDES / master_profile / draft) before "
          "rendering or sharing. See .claude/skills/resume-integrity/SKILL.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
