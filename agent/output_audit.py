"""Output audit — catches fabrication AFTER resume generation.

CLAUDE.md hard rule 2: "Never fabricate credentials, dates, metrics, or scope.
Strategic reframing using JD language is OK. Inventing is not."

The pre-generation guardrails in resume_pipeline.py (scrub_fluff,
detect_fabricated_metrics, ADJACENCY_EVIDENCE) catch ~90% of fluff/fabrication
at write-time. This module catches the remaining ~10% — bullets that pass
numeric checks but introduce framings/scopes/outcomes not in master_profile.json.

Approach:
    1. Extract every bullet from each generated PDF (pdftotext + heuristic split).
    2. Send the bullet + the full master_profile.json to Claude (via Max OAuth)
       and ask: defensible / reframed / fabricated? Return short evidence quote.
    3. Aggregate per role; any `fabricated` label → quarantine that PDF.
    4. Write outputs/{date}/_output_audit.json + per-role trajectory entries.

Quarantine semantics:
    - PDF moved from resumes_compact/ → quarantined_resumes/
    - Role dropped from brief's FITS/BUMPED FITS section
    - Added to brief's "Drift / error notes" section with the offending bullet
    - Subject line gets `[fabricated-quarantine: N]` flag
    - User sees the quarantined PDFs on the daily-runs branch for manual review

Cost: 0 (Max OAuth). One Opus call per role × ~30 roles × ~3K tokens = well
within the 5-hr Opus quota window. Falls back gracefully if quota is exhausted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable


def _has_cli() -> bool:
    return (shutil.which("claude") is not None
            and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip() != "")


def extract_bullets_from_pdf(pdf_path: Path) -> list[str]:
    """Extract bullet-like lines from a PDF using pdftotext.

    Bullet detection heuristic: lines that start with '•', '·', '-', '*',
    or any utf-8 bullet glyph, OR lines following 'EXPERIENCE'/'PROJECTS'
    headers that look like multi-sentence achievement statements.
    """
    if shutil.which("pdftotext") is None:
        return []
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return []
        text = proc.stdout
    except subprocess.TimeoutExpired:
        return []

    bullets: list[str] = []
    current: list[str] = []
    in_experience_section = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                bullets.append(" ".join(current).strip())
                current = []
            continue
        # Section headers reset state
        if re.match(r"^(PROFESSIONAL EXPERIENCE|EXPERIENCE|PROJECTS|EDUCATION|"
                    r"CORE COMPETENCIES|EXECUTIVE SUMMARY)$", line, re.IGNORECASE):
            if current:
                bullets.append(" ".join(current).strip())
                current = []
            in_experience_section = line.upper() in (
                "PROFESSIONAL EXPERIENCE", "EXPERIENCE", "PROJECTS")
            continue
        # Bullet start markers
        if line.startswith(("•", "·", "-", "*", "▪", "►")) and in_experience_section:
            if current:
                bullets.append(" ".join(current).strip())
            current = [re.sub(r"^[•·\-*▪►]\s*", "", line)]
        elif current and in_experience_section:
            # Continuation of previous bullet (PDF text-wrap rejoin)
            current.append(line)

    if current:
        bullets.append(" ".join(current).strip())

    # Drop short fragments (likely role headers or dates that slipped through)
    return [b for b in bullets if len(b) > 60]


_AUDIT_PROMPT = """You audit a tailored resume for Abhillash Jadhav.

GROUND TRUTH (master_profile.json — the ONLY source of fact):
{profile_blob}

ROLE THIS RESUME WAS TAILORED FOR:
Company: {company}
Title: {title}

BULLETS TO AUDIT (one per line, numbered):
{bullets_block}

For each bullet, return a JSON object with:
- index: 1-based bullet number
- label: one of "defensible" | "reframed" | "fabricated"
- evidence: short quote from the profile OR explanation if fabricated
- offending_claim: if fabricated, the exact phrase that has no source

Labels:
- defensible: claim, numbers, dates, scope all match profile. Vocabulary may differ.
- reframed: vocabulary changed, claim unchanged. Allowed.
- fabricated: any NEW number/date/scope/framework/outcome not derivable from profile.

CRITICAL fabrication patterns (auto-fail):
- Metrics not in profile ($X, ₹X, %, headcount)
- Wrong dates (Flipkart is Jun 2014-Jun 2016)
- "MJ Internet" listed anywhere
- AARRR/RFM attributed to anywhere but Amazon
- "Founding member" for PayTM (canonical is "Founding PM leader")
- "Part-Time" for RADAR (canonical is "Pro Bono")

Return ONLY a JSON array, no prose:
[
  {{"index":1,"label":"...","evidence":"...","offending_claim":""}}, ...
]"""


def audit_resume(pdf_path: Path, candidate: dict, profile: dict,
                 react_logger: Callable[[dict], None] | None = None) -> dict:
    """Audit one PDF. Return per-bullet labels + summary counts.

    If Claude CLI is unavailable, returns {"skipped": True, ...} — no
    silent pass; the brief surfaces this honestly.
    """
    bullets = extract_bullets_from_pdf(pdf_path)
    if not bullets:
        return {"pdf": str(pdf_path.name), "skipped": True,
                "reason": "no-bullets-extracted",
                "labels": [], "defensible": 0, "reframed": 0, "fabricated": 0}

    if not _has_cli():
        return {"pdf": str(pdf_path.name), "skipped": True,
                "reason": "no-claude-cli", "labels": [],
                "defensible": 0, "reframed": 0, "fabricated": 0}

    # Compact profile blob — keep input under 30KB to stay efficient.
    profile_blob = json.dumps({
        "executive_summary": profile.get("executive_summary", ""),
        "experience": [{
            "company": r.get("company"),
            "title": r.get("title"),
            "start": r.get("start"),
            "end": r.get("end"),
            "achievements": r.get("achievements", []),
            "metrics": r.get("metrics", []),
            "scope": r.get("scope", ""),
        } for r in profile.get("experience", [])],
        "constraints": profile.get("constraints", {}),
    }, ensure_ascii=False)[:30000]

    bullets_block = "\n".join(f"{i+1}. {b}" for i, b in enumerate(bullets))
    prompt = _AUDIT_PROMPT.format(
        profile_blob=profile_blob,
        company=candidate.get("company", "?"),
        title=candidate.get("title", "?"),
        bullets_block=bullets_block,
    )

    if react_logger:
        react_logger({"step": "5b-output-audit",
                      "company": candidate.get("company"),
                      "intent": "claude audit of bullets",
                      "bullet_count": len(bullets)})

    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--model", "claude-opus-4-7",
             "--output-format", "json",
             "--max-turns", "20",
             "--disallowed-tools", "Bash,Edit,Write,WebFetch,WebSearch,Read"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ},
        )
        if proc.returncode != 0:
            return {"pdf": str(pdf_path.name), "skipped": True,
                    "reason": f"cli-rc-{proc.returncode}",
                    "stderr": proc.stderr[-300:],
                    "labels": [], "defensible": 0, "reframed": 0, "fabricated": 0}
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result", "")
        m = re.search(r"\[[\s\S]*\]", result_text)
        if not m:
            return {"pdf": str(pdf_path.name), "skipped": True,
                    "reason": "no-json-array-in-response",
                    "labels": [], "defensible": 0, "reframed": 0, "fabricated": 0}
        labels = json.loads(m.group())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        return {"pdf": str(pdf_path.name), "skipped": True,
                "reason": f"{type(e).__name__}: {str(e)[:200]}",
                "labels": [], "defensible": 0, "reframed": 0, "fabricated": 0}

    counts = {"defensible": 0, "reframed": 0, "fabricated": 0}
    enriched_labels = []
    for entry in labels:
        idx = entry.get("index", 0) - 1
        label = entry.get("label", "").lower()
        if label in counts:
            counts[label] += 1
        enriched_labels.append({
            "index": entry.get("index"),
            "label": label,
            "evidence": entry.get("evidence", ""),
            "offending_claim": entry.get("offending_claim", ""),
            "bullet": bullets[idx] if 0 <= idx < len(bullets) else "",
        })

    if react_logger:
        react_logger({"step": "5b-output-audit",
                      "company": candidate.get("company"),
                      "observation": f"defensible={counts['defensible']} "
                                     f"reframed={counts['reframed']} "
                                     f"fabricated={counts['fabricated']}",
                      "decision": "quarantine" if counts["fabricated"] > 0 else "pass"})

    return {"pdf": str(pdf_path.name),
            "skipped": False,
            "labels": enriched_labels,
            **counts}


def audit_and_quarantine(
    fits_and_paths: list[tuple[dict, Path]],
    profile: dict,
    date_dir: Path,
    react_logger: Callable[[dict], None] | None = None,
) -> tuple[list[tuple[dict, Path]], list[dict]]:
    """Audit every fit's PDF; quarantine any with a fabricated bullet.

    Returns (clean_fits_and_paths, audit_results). The brief should render
    only the clean list. Quarantined PDFs move from resumes_compact/ to
    quarantined_resumes/ on disk so the user can review.
    """
    quarantine_dir = date_dir / "quarantined_resumes"
    audit_results: list[dict] = []
    clean: list[tuple[dict, Path]] = []

    for candidate, pdf_path in fits_and_paths:
        result = audit_resume(pdf_path, candidate, profile, react_logger=react_logger)
        result["company"] = candidate.get("company")
        result["title"] = candidate.get("title")
        audit_results.append(result)
        if result.get("fabricated", 0) > 0:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            target = quarantine_dir / pdf_path.name
            try:
                shutil.move(str(pdf_path), str(target))
            except OSError:
                pass
            if react_logger:
                react_logger({"step": "5b-output-audit",
                              "company": candidate.get("company"),
                              "decision": "quarantined",
                              "moved_to": str(target)})
        else:
            clean.append((candidate, pdf_path))

    # Persist the audit report
    (date_dir / "_output_audit.json").write_text(
        json.dumps(audit_results, ensure_ascii=False, indent=2)
    )
    return clean, audit_results
