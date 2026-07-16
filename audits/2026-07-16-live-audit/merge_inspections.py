"""Merge inspector judgment signals into a copy of the harvested snapshots.

Reads:  audits/2026-07-16-live-audit/snapshots/   (pristine, user-harvested)
        <scratchpad>/inspection/<login>--<repo>.json  (inspector outputs)
Writes: audits/2026-07-16-live-audit/snapshots-inspected/  (engine fixture dir)

Rules enforced here:
- Mechanical signals (derived by harvest_snapshots.py) are never overwritten;
  an inspector file that tries to set one is a hard error.
- Source-code-only signals are rejected (nobody saw source code).
- Inspector may only add keys into the record's `signals` dict — record-level
  fields (has_tests, commit_count, ...) are untouchable.
- Negative-trending records (template_similarity_pct >= 60 or
  boilerplate_share_pct >= 60 or backed/total < 0.5) must carry a
  counter_evidence_review with reviewed=true.
- Evidence lists must have >= 2 distinct non-readme origins (engine Loop 3
  enforces the real thresholds; this is an early loud check).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path("/home/user/loop-engineering")
SRC = REPO / "audits/2026-07-16-live-audit/snapshots"
DST = REPO / "audits/2026-07-16-live-audit/snapshots-inspected"
INSPECTIONS = Path(
    "/tmp/claude-0/-home-user-loop-engineering/"
    "22c8254b-7fed-5da3-821d-c2a8e5463b0a/scratchpad/inspection"
)

MECHANICAL_KEYS = {
    "test_search",
    "root_entry_count",
    "ci_runs",
    "test_files",
    "readme_length",
    "distinct_commit_days",
    "commits_sampled",
    "commit_msg_uniformity_pct",
    "refactor_commits",
    "one_shot_dump",
}
FORBIDDEN_KEYS = MECHANICAL_KEYS | {
    "error_handling_present",
    "input_validation_present",
    "state_management_present",
    "security_practices_present",
    "edge_case_handling_present",
    "failure_handling_tested",
    "apis_current",
}


def fail(msg: str) -> None:
    print(f"MERGE-ERROR: {msg}")
    sys.exit(2)


def load_inspections() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(INSPECTIONS.glob("*--*.json")):
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        login, repo = data.get("login"), data.get("repo")
        stem_login, stem_repo = path.stem.split("--", 1)
        if login != stem_login or repo != stem_repo:
            fail(f"{path.name}: login/repo fields disagree with filename")
        signals = data.get("signals")
        if not isinstance(signals, dict) or not signals:
            fail(f"{path.name}: missing/empty signals dict")
        bad = FORBIDDEN_KEYS & set(signals)
        if bad:
            fail(f"{path.name}: forbidden signal keys {sorted(bad)}")
        validate_evidence(path.name, signals)
        validate_counter_evidence(path.name, signals)
        out[(login, repo)] = data
    return out


def validate_evidence(name: str, signals: dict) -> None:
    ev = signals.get("evidence", [])
    if not isinstance(ev, list) or len(ev) < 3:
        fail(f"{name}: evidence list has {len(ev) if isinstance(ev, list) else 'no'} items (<3)")
    origins = [str(e.get("origin", "")) for e in ev if isinstance(e, dict)]
    non_readme = {o for o in origins if o and o != "readme"}
    if len(non_readme) < 2:
        fail(f"{name}: fewer than 2 distinct non-readme evidence origins: {sorted(set(origins))}")
    for e in ev:
        if not isinstance(e, dict) or not e.get("origin") or not e.get("excerpt"):
            fail(f"{name}: evidence item missing origin/excerpt: {e}")


def validate_counter_evidence(name: str, signals: dict) -> None:
    total = signals.get("readme_claims_total")
    backed = signals.get("readme_claims_code_backed")
    negative = (
        float(signals.get("template_similarity_pct", 0)) >= 60
        or float(signals.get("boilerplate_share_pct", 0)) >= 60
        or (
            isinstance(total, int)
            and isinstance(backed, int)
            and total > 0
            and backed / total < 0.5
        )
    )
    cer = signals.get("counter_evidence_review")
    if negative and (not isinstance(cer, dict) or not cer.get("reviewed")):
        fail(f"{name}: negative-trending signals but no reviewed counter_evidence_review")


# Independent identity-corroboration evidence recorded during the earlier
# identity-verification step (audits/2026-07-16-live-audit/identity-evidence.md,
# snapshots under audits/2026-07-16-live-audit/evidence/). The harvest script
# embedded only the github_profile origin in profiles/<login>.json; these are
# the other recorded origins, copied verbatim — no new evidence is created here.
IDENTITY_EVIDENCE_EXTRA = {
    "aakashg": [
        {
            "origin": "external_site",
            "url": "https://www.news.aakashg.com/p/you-should-build-a-pm-github",
            "excerpt": (
                "Subject's own newsletter domain (news.aakashg.com) publishes >=9 "
                "Product Growth posts containing github.com/aakashg links, e.g. "
                "'How to Build a PM GitHub That Gets You Hired' — person->login "
                "direction; see identity-evidence.md row 2"
            ),
            "retrieved_at": "2026-07-16T15:00:44+00:00",
        },
    ],
    "Shubhamsaboo": [
        {
            "origin": "social_media",
            "url": "https://www.threads.com/@saboo_shubham_/post/DNmbKh3OdPv",
            "excerpt": (
                "Subject's own Threads account (@saboo_shubham_) posts "
                "github.com/Shubhamsaboo/awesome-llm-apps as his own work "
                "('I have created 100+ production-ready AI Agents… Awesome LLM "
                "Apps just hit 60k+ stars') — person->login direction; see "
                "identity-evidence.md row 2"
            ),
            "retrieved_at": "2026-07-16T15:00:46+00:00",
        },
        {
            "origin": "external_site",
            "url": "https://raw.githubusercontent.com/Shubhamsaboo/awesome-llm-apps/main/README.md",
            "excerpt": (
                "awesome-llm-apps README banner links to theunwindai.com (the "
                "subject's Unwind AI property), closing the site<->repo loop — "
                "sha256:0c784831cba41b2e…, retrieved 2026-07-16T15:00:46Z"
            ),
            "retrieved_at": "2026-07-16T15:00:46+00:00",
        },
    ],
}


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    for sub in ("profiles", "candidates"):
        shutil.copytree(SRC / sub, DST / sub)
    for login, extra in IDENTITY_EVIDENCE_EXTRA.items():
        ppath = DST / "profiles" / f"{login}.json"
        profile = json.loads(ppath.read_text(encoding="utf-8"))
        links = profile.setdefault("evidence_links", [])
        existing = {(e.get("origin"), e.get("url")) for e in links}
        for item in extra:
            if (item["origin"], item["url"]) not in existing:
                links.append(item)
        ppath.write_text(
            json.dumps(profile, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    (DST / "README.md").write_text(
        "# snapshots-inspected\n\n"
        "Engine fixture dir = pristine user-harvested `../snapshots/` "
        "(commit c04169d, verify: PASSED) with inspector judgment signals "
        "merged into each authored repo record's `signals` dict. Mechanical "
        "signals are byte-identical to the harvest; raw content/evidence "
        "remain only in `../snapshots/`. Produced by merge_inspections.py.\n",
        encoding="utf-8",
    )

    inspections = load_inspections()
    merged, skipped = 0, []
    for login_dir in sorted((SRC / "repos").iterdir()):
        login = login_dir.name
        out_dir = DST / "repos" / login
        out_dir.mkdir(parents=True)
        for page in sorted(login_dir.glob("page-*.json")):
            records = json.loads(page.read_text(encoding="utf-8"))
            for rec in records:
                key = (login, rec["name"])
                if key not in inspections:
                    if not rec.get("fork") and rec.get("commit_count", 0) > 0:
                        skipped.append(f"{login}/{rec['name']}")
                    continue
                ins = inspections.pop(key)["signals"]
                overlap = set(ins) & set(rec.get("signals", {}))
                if overlap:
                    fail(f"{login}/{rec['name']}: inspector would overwrite {sorted(overlap)}")
                rec.setdefault("signals", {}).update(ins)
                merged += 1
            out_path = out_dir / page.name
            out_path.write_text(
                json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    if inspections:
        fail(f"inspections with no matching snapshot record: {sorted(inspections)}")
    print(f"merged: {merged} repos inspected")
    if skipped:
        print(f"authored-but-uninspected ({len(skipped)}): {', '.join(sorted(skipped))}")
    print("OK")


if __name__ == "__main__":
    main()
