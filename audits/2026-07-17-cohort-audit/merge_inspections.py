"""Assemble the cohort engine fixture: snapshots + inspections + reuse.

Reads:  audits/2026-07-17-cohort-audit/snapshots/        (pristine harvest @ df5145b)
        <scratchpad>/cohort-inspection/<login>--<repo>.json  (inspector outputs)
        audits/2026-07-16-live-audit/snapshots-inspected/    (completed-audit reuse:
            aakashg + Shubhamsaboo records with judgment signals, enriched profiles)
Writes: audits/2026-07-17-cohort-audit/snapshots-inspected/  (engine fixture dir)

Rules enforced (same as the completed audit's merge, plus deep-inspection
labeling):
- mechanical signals are never overwritten; forbidden/source-code-only keys
  rejected; record-level fields untouchable;
- negative-trending inspections must carry a reviewed counter_evidence_review;
- evidence lists need >=3 items with >=2 distinct non-readme origins;
- every authored record gets signals["deep_inspected"] (true only where
  judgment signals exist), so uninspected repos are labeled, never implied;
- aakash-gupta / shubham-saboo records are copied VERBATIM from the completed
  audit's fixture (their audit is not reopened);
- profile evidence_links are enriched ONLY with origins already recorded in
  identity-evidence.md; Abhillashjadhav gets no enrichment (no independent
  person->login channel exists — disclosed, not papered over).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path("/home/user/loop-engineering")
SRC = REPO / "audits/2026-07-17-cohort-audit/snapshots"
DST = REPO / "audits/2026-07-17-cohort-audit/snapshots-inspected"
REUSE = REPO / "audits/2026-07-16-live-audit/snapshots-inspected"
INSPECTIONS = Path(
    "/tmp/claude-0/-home-user-loop-engineering/"
    "22c8254b-7fed-5da3-821d-c2a8e5463b0a/scratchpad/cohort-inspection"
)
REUSED_LOGINS = {"aakashg", "Shubhamsaboo"}

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
    "deep_inspected",
}

# Independent identity origins recorded in identity-evidence.md (2026-07-17,
# indexed-search corroboration ~03:44-03:55Z). Copied verbatim — nothing new.
IDENTITY_EVIDENCE_EXTRA = {
    "phuryn": [
        {
            "origin": "external_site",
            "url": "https://www.productcompass.pm/p/pm-skills-2-red-team-ship",
            "excerpt": (
                "Subject's own newsletter domain (productcompass.pm, 'The Product "
                "Compass | Pawel Huryn') publishes posts presenting "
                "github.com/phuryn/pm-skills and pm-brain as his work — "
                "person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
    ],
    "hamelsmu": [
        {
            "origin": "external_site",
            "url": "https://hamel.dev/",
            "excerpt": (
                "Subject's own blog hamel.dev links github.com/hamelsmu "
                "repositories as his (evals-skills post; notes cookbook) — "
                "person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
    ],
    "eugeneyan": [
        {
            "origin": "external_site",
            "url": "https://eugeneyan.com/writing/obsidian-copilot/",
            "excerpt": (
                "Subject's own site eugeneyan.com links github.com/eugeneyan "
                "repos as his projects (obsidian-copilot, testing-ml, "
                "news-agents, /prototyping/) — person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
    ],
    "shreyashankar": [
        {
            "origin": "external_site",
            "url": "https://www.sh-reya.com/SS_CV.pdf",
            "excerpt": (
                "Subject's own site CV ('Shreya Shankar shreyashankar@berkeley.edu "
                "| sh-reya.com') and site footer link her GitHub profile — "
                "person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
        {
            "origin": "social_media",
            "url": "https://x.com/sh_reya/status/1838617845246366131",
            "excerpt": (
                "Subject's own X account @sh_reya (linked from sh-reya.com) "
                "promotes her GitHub work ('star our Github repo!') — "
                "person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
    ],
    "chiphuyen": [
        {
            "origin": "external_site",
            "url": "https://huyenchip.com/ml-interviews-book/",
            "excerpt": (
                "Subject's own site huyenchip.com links github.com/chiphuyen "
                "repositories as hers (ml-interviews-book -> coding-exercises; "
                "open-sourced book repos named in her profile README) — "
                "person->login; identity-evidence.md"
            ),
            "retrieved_at": "2026-07-17T03:50:00+00:00",
        },
    ],
    # Abhillashjadhav: intentionally ABSENT — no independent person->login
    # channel exists as of 2026-07-17 (identity-evidence.md); the identity
    # claim will carry one independent origin and Loop 3 will say so.
}


def fail(msg: str) -> None:
    print(f"MERGE-ERROR: {msg}")
    sys.exit(2)


def validate_evidence(name: str, signals: dict) -> None:
    ev = signals.get("evidence", [])
    if not isinstance(ev, list) or len(ev) < 3:
        fail(f"{name}: evidence list has {len(ev) if isinstance(ev, list) else 'no'} items (<3)")
    origins = [str(e.get("origin", "")) for e in ev if isinstance(e, dict)]
    non_readme = {o for o in origins if o and o != "readme"}
    if len(non_readme) < 2:
        fail(f"{name}: fewer than 2 distinct non-readme origins: {sorted(set(origins))}")
    for e in ev:
        if not isinstance(e, dict) or not e.get("origin") or not e.get("excerpt"):
            fail(f"{name}: evidence item missing origin/excerpt")
    ce = signals.get("counter_evidence", [])
    if not isinstance(ce, list) or any(
        not isinstance(e, dict) or not e.get("origin") or not e.get("excerpt") for e in ce
    ):
        fail(f"{name}: counter_evidence must be a list of {{origin,url,excerpt}} objects")


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


def load_inspections() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(INSPECTIONS.glob("*--*.json")):
        if path.name.startswith("COMPARISON--"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
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


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    shutil.copytree(SRC / "candidates", DST / "candidates")

    # Profiles: cohort harvest, with identity-evidence enrichment; the two
    # reused logins take their enriched profiles from the completed audit.
    (DST / "profiles").mkdir()
    for ppath in sorted((SRC / "profiles").glob("*.json")):
        login = ppath.stem
        source = REUSE / "profiles" / f"{login}.json" if login in REUSED_LOGINS else ppath
        profile = json.loads(source.read_text(encoding="utf-8"))
        links = profile.setdefault("evidence_links", [])
        existing = {(e.get("origin"), e.get("url")) for e in links}
        for item in IDENTITY_EVIDENCE_EXTRA.get(login, []):
            if (item["origin"], item["url"]) not in existing:
                links.append(item)
        (DST / "profiles" / ppath.name).write_text(
            json.dumps(profile, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    inspections = load_inspections()
    merged, reused, uninspected = 0, 0, []
    for login_dir in sorted((SRC / "repos").iterdir()):
        login = login_dir.name
        out_dir = DST / "repos" / login
        if login in REUSED_LOGINS:
            shutil.copytree(REUSE / "repos" / login, out_dir)
            for page in sorted(out_dir.glob("page-*.json")):
                records = json.loads(page.read_text(encoding="utf-8"))
                for rec in records:
                    sig = rec.setdefault("signals", {})
                    sig["deep_inspected"] = bool(
                        set(sig) - MECHANICAL_KEYS - {"deep_inspected"}
                    )
                    reused += 1
                page.write_text(
                    json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
                )
            continue
        out_dir.mkdir(parents=True)
        for page in sorted(login_dir.glob("page-*.json")):
            records = json.loads(page.read_text(encoding="utf-8"))
            for rec in records:
                key = (login, rec["name"])
                sig = rec.setdefault("signals", {})
                if key in inspections:
                    ins = inspections.pop(key)["signals"]
                    overlap = set(ins) & set(sig)
                    if overlap:
                        fail(f"{login}/{rec['name']}: would overwrite {sorted(overlap)}")
                    sig.update(ins)
                    sig["deep_inspected"] = True
                    merged += 1
                else:
                    sig["deep_inspected"] = False
                    if not rec.get("fork") and rec.get("commit_count", 0) > 0:
                        uninspected.append(f"{login}/{rec['name']}")
            (out_dir / page.name).write_text(
                json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    if inspections:
        fail(f"inspections with no matching snapshot record: {sorted(inspections)}")

    # Cohort report inputs: the inspector-recorded 12-dimension comparison and
    # the operator audit config, consumed by cohort_report.py at z-2 time.
    comp_dir = DST / "comparisons"
    comp_dir.mkdir()
    for cpath in sorted(INSPECTIONS.glob("COMPARISON--*.json")):
        comp = json.loads(cpath.read_text(encoding="utf-8"))
        for key, dim in comp.get("dimensions", {}).items():
            if dim.get("favors") not in {"pm_skills", "pm_agent_os", "parity", "insufficient"}:
                fail(f"{cpath.name}: dimension {key} lacks a valid 'favors' value")
        (comp_dir / cpath.name.replace("COMPARISON--", "")).write_text(
            json.dumps(comp, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    shutil.copyfile(
        REPO / "audits/2026-07-17-cohort-audit/audit-config.yaml",
        DST / "audit-config.yaml",
    )

    (DST / "README.md").write_text(
        "# snapshots-inspected (cohort)\n\n"
        "Engine fixture = pristine user harvest (../snapshots @ df5145b, "
        "verify: PASSED) + inspector judgment signals for the deterministic "
        "deep-inspection set + verbatim reuse of the completed 2026-07-16 "
        "audit's records for aakashg/Shubhamsaboo. Every authored record "
        "carries signals.deep_inspected; false means mechanical-signals-only "
        "evidence. Produced by merge_inspections.py (this directory).\n",
        encoding="utf-8",
    )
    print(f"merged: {merged} newly inspected; reused records: {reused}")
    print(f"authored-but-not-deep-inspected ({len(uninspected)}) — labeled deep_inspected=false")
    print("OK")


if __name__ == "__main__":
    main()
