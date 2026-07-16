"""LLM-driven resume generator — generate -> critique -> iterate.

Replaces the deterministic governance/reframing pipeline. The meta-goal is
a resume that makes a recruiter pick up the phone for a strong-fit role:
when a design choice helps audit accuracy but hurts call-back odds,
call-back odds win.

Three stages, all driven by Claude via the `claude` CLI (Max-plan OAuth, $0):

  1. Generator  (generate_draft)  — master_profile.json + JD -> a resume draft.
  2. Critic     (critique_draft)  — JD + draft -> per-bullet critique on six
                                    dimensions plus a 0-100 fitment score.
  3. Controller (iterate)         — generate, critique, apply, re-critique;
                                    up to 3 rounds or until the fitment
                                    delta between consecutive rounds is <5.

A hybrid fabrication check (fabrication_check) runs every round: a
deterministic numeric-token pass plus an LLM claim-classification pass.
Every bullet lands in an output ledger as traced / jd_adjacent /
unverifiable. Unverifiable claims are fed back as critique and never ship.

Honesty contract (CLAUDE.md Hard Rule 2): the generator may only restate
facts present in master_profile.json. Reframing into JD vocabulary is
allowed; inventing metrics, scope, dates, headcount, or budget is not.

Transport: when CLAUDE_CODE_OAUTH_TOKEN is absent the LLM calls are
unavailable; callers fall back to the deterministic agent/resume_pipeline.py
renderer. `llm_available()` reports this.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile" / "master_profile.json"

MODEL = "claude-opus-4-7"
MAX_ROUNDS = 3
# Stop iterating once the fitment score moves <5 points between rounds —
# further rounds are not buying meaningful call-back lift.
FITMENT_DELTA_STOP = 5

# A runner takes a prompt and returns the model's text reply, or None on
# failure. The default is the Claude CLI; tests inject a deterministic stub.
Runner = Callable[[str], "str | None"]


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------

def llm_available() -> bool:
    """True when the Claude CLI can be invoked under the user's Max plan."""
    return (shutil.which("claude") is not None
            and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip() != "")


def _run_claude(prompt: str, *, timeout: int = 180, max_turns: int = 20) -> str | None:
    """Invoke `claude -p` and return the assistant's final text, or None.

    Mirrors agent/scorer.py — `--output-format json` returns an envelope
    `{type, ..., result}`; `result` is the assistant's reply text.
    """
    if not llm_available():
        return None
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--model", MODEL,
             "--output-format", "json",
             "--max-turns", str(max_turns),
             "--disallowed-tools", "Bash,Edit,Write,WebFetch,WebSearch,Read"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ},
        )
        if proc.returncode != 0:
            return None
        envelope = json.loads(proc.stdout)
        return envelope.get("result") or None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None


def _extract_json(text: str | None) -> dict | None:
    """Pull the first balanced JSON object out of a model reply."""
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        obj = json.loads(m.group())
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Profile digest — the fact base handed to the generator
# --------------------------------------------------------------------------

def _profile_digest(profile: dict) -> str:
    """A compact, fact-only view of master_profile.json for the prompt.

    Deliberately excludes the canonical_facts block (the generator works
    from the human-readable experience entries) but includes constraints —
    the hard wording rules the resume must honor.
    """
    roles = []
    for r in profile.get("experience", []):
        roles.append({
            "company": r.get("company"),
            "title": r.get("title"),
            "dates": f'{r.get("start", "")} - {r.get("end", "")}'.strip(" -"),
            "scope": r.get("scope", ""),
            "metrics": r.get("metrics", []),
            "achievements": r.get("achievements", []),
        })
    digest = {
        "executive_summary": profile.get("executive_summary", ""),
        "experience": roles,
        "selected_projects": profile.get("selected_projects", []),
        "education": profile.get("education", ""),
        "constraints": profile.get("constraints", {}),
    }
    return json.dumps(digest, ensure_ascii=False, indent=1)


def role_companies(profile: dict) -> list[str]:
    """Company names in master_profile experience order (drives render order)."""
    return [r.get("company", "") for r in profile.get("experience", [])]


# --------------------------------------------------------------------------
# Stage 1 — Generator
# --------------------------------------------------------------------------

_DRAFT_SCHEMA = """{
  "executive_summary": "3-4 sentence summary, JD-aligned, no hype",
  "core_skills": ["skill", "skill", ...],
  "roles": [
    {"company": "<exact company name from the profile>",
     "bullets": ["X-Y-Z framed bullet", ...]}
  ],
  "core_competencies": [["Label", "kw · kw · kw"], ...]
}"""


def _generator_prompt(profile: dict, jd: str,
                      critique: dict | None,
                      fab_findings: dict | None) -> str:
    digest = _profile_digest(profile)
    companies = ", ".join(c for c in role_companies(profile) if c)
    parts = [
        "You are an expert resume writer. Write a tailored resume draft for "
        "Abhillash Jadhav for the job description below.",
        "",
        "META-GOAL: the resume must make a recruiter pick up the phone for a "
        "strong-fit role. Optimise for call-back odds, not for audit "
        "tidiness.",
        "",
        "HONESTY (non-negotiable): every claim must be defensible against the "
        "FACT BASE below. Reframing a real achievement into the JD's "
        "vocabulary is encouraged. Inventing metrics, scope, dates, "
        "headcount, budget, named systems, or titles is forbidden. If the JD "
        "wants something the fact base does not support, leave it out — do "
        "not paper over the gap.",
        "",
        "BULLET CRAFT:",
        "- Frame every experience bullet X-Y-Z: accomplished [X], measured by "
        "[Y], by doing [Z]. The mechanism (Z) must be concrete and credible.",
        "- Lead each bullet with a strong, specific verb. Vary the lead verbs "
        "within a role — no two bullets in the same role start the same way.",
        "- Put the number/scope where a 6-second scan will catch it.",
        "- No hype adjectives (world-class, cutting-edge, passionate, etc.).",
        "- Honor the wording in constraints exactly (titles, the '11+ years' "
        "framing, never list MJ Internet Pvt Ltd).",
        "",
        f"FACT BASE (master_profile.json digest):\n{digest}",
        "",
        f"JOB DESCRIPTION:\n{jd.strip()[:6000]}",
        "",
        f"Use exactly these companies, in this order, in `roles`: {companies}.",
        "Each role gets 2-4 bullets (most recent / most relevant roles get "
        "more; oldest roles get 1-2).",
    ]
    if critique:
        parts += [
            "",
            "REVISION — apply this critique from the previous round. Fix every "
            "bullet marked 'revise' or 'cut'; keep what scored well:",
            json.dumps(critique, ensure_ascii=False, indent=1)[:6000],
        ]
    if fab_findings and fab_findings.get("unverifiable"):
        parts += [
            "",
            "FABRICATION FINDINGS — these claims did NOT trace to the fact "
            "base. Rewrite them to a defensible claim or cut them entirely:",
            json.dumps(fab_findings["unverifiable"], ensure_ascii=False)[:3000],
        ]
    parts += [
        "",
        f"Return ONLY a JSON object in this shape (no prose):\n{_DRAFT_SCHEMA}",
    ]
    return "\n".join(parts)


def generate_draft(profile: dict, jd: str, *,
                   critique: dict | None = None,
                   fab_findings: dict | None = None,
                   runner: Runner | None = None) -> dict | None:
    """LLM call #1 — produce a resume draft. Returns the draft dict or None."""
    runner = runner or _run_claude
    prompt = _generator_prompt(profile, jd, critique, fab_findings)
    draft = _extract_json(runner(prompt))
    if not draft or "roles" not in draft:
        return None
    return draft


# --------------------------------------------------------------------------
# Stage 2 — Critic
# --------------------------------------------------------------------------

# The six per-bullet critique dimensions. Each scored 1 (poor) - 5 (excellent).
CRITIQUE_DIMENSIONS = (
    "jd_intent_match",       # speaks to what THIS JD actually wants
    "outcome_specificity",   # concrete outcome + strong, role-distinct lead verb
    "mechanism_credibility",  # X-Y-Z: the 'how' is present and believable
    "scale_legibility",      # numbers/scope legible in a 6-second scan
    "tone_fit",              # matches the seniority/voice the JD implies
    "fabrication_trace",     # every claim traces to master_profile.json
)

_CRITIQUE_SCHEMA = """{
  "fitment": 0-100,
  "overall": "2-3 sentences: would this resume earn a recruiter call?",
  "bullets": [
    {"ref": "<Company>#<n>", "text": "...",
     "scores": {"jd_intent_match":1-5, "outcome_specificity":1-5,
                "mechanism_credibility":1-5, "scale_legibility":1-5,
                "tone_fit":1-5, "fabrication_trace":1-5},
     "verdict": "keep|revise|cut",
     "fix": "specific, actionable instruction (empty if verdict=keep)"}
  ]
}"""


def _bullet_refs(draft: dict) -> list[dict]:
    """Flatten a draft's bullets to {ref, company, text} for the critic."""
    out = []
    for role in draft.get("roles", []):
        company = role.get("company", "?")
        for i, b in enumerate(role.get("bullets", []) or [], 1):
            out.append({"ref": f"{company}#{i}", "company": company, "text": b})
    return out


def _critic_prompt(jd: str, draft: dict) -> str:
    refs = _bullet_refs(draft)
    return "\n".join([
        "You are a hiring-side resume critic. Judge this resume draft for the "
        "job description below, through one lens: would it make a recruiter "
        "pick up the phone for a strong-fit candidate?",
        "",
        "Score each experience bullet 1 (poor) to 5 (excellent) on SIX "
        "dimensions:",
        "- jd_intent_match: does the bullet speak to what THIS JD actually "
        "wants, not generic PM work?",
        "- outcome_specificity: a concrete outcome (not an activity); the "
        "lead verb is strong and distinct from sibling bullets in the role.",
        "- mechanism_credibility: X-Y-Z — is the 'how' (the mechanism) "
        "present and believable?",
        "- scale_legibility: are the numbers/scope legible in a 6-second "
        "scan, or buried?",
        "- tone_fit: does the voice match the seniority the JD implies — no "
        "hype, no fluff, no under-selling?",
        "- fabrication_trace: does every claim look like a real, traceable "
        "achievement (5) or an invented one (1)?",
        "",
        "Give each bullet a verdict: keep / revise / cut, and a specific fix "
        "for anything below 'keep'. Then give the whole resume a fitment "
        "score 0-100 — the probability-weighted strength of this resume for "
        "THIS role, recruiter-callback lens.",
        "",
        f"JOB DESCRIPTION:\n{jd.strip()[:6000]}",
        "",
        f"EXECUTIVE SUMMARY:\n{draft.get('executive_summary', '')}",
        "",
        "BULLETS:\n" + "\n".join(f'{r["ref"]}: {r["text"]}' for r in refs),
        "",
        f"Return ONLY a JSON object in this shape (no prose):\n{_CRITIQUE_SCHEMA}",
    ])


def critique_draft(jd: str, draft: dict, *,
                   runner: Runner | None = None) -> dict | None:
    """LLM call #2 — critique a draft. Returns the critique dict or None."""
    runner = runner or _run_claude
    crit = _extract_json(runner(_critic_prompt(jd, draft)))
    if not crit or "fitment" not in crit:
        return None
    try:
        crit["fitment"] = max(0, min(100, int(crit["fitment"])))
    except (TypeError, ValueError):
        return None
    return crit


# --------------------------------------------------------------------------
# Hybrid fabrication check + output ledger
# --------------------------------------------------------------------------

_NUM_RE = re.compile(
    r"\$[\d.,]+\s*[BMK]?|₹[\d.,]+\s*Cr?|Rs\.?\s*[\d.,]+\s*Cr?|"
    r"[+\-]?\d[\d.,]*\s*%|[+\-]?\d[\d.,]*\s*bps|"
    r"\b\d[\d,]*\+?\s*[BMK]\b|\b\d[\d,]{3,}\+?\b",
    re.IGNORECASE,
)


def _profile_number_blob(profile: dict) -> str:
    """Every numeric-bearing string in the profile, lower-cased, concatenated."""
    parts = [profile.get("executive_summary", "")]
    for r in profile.get("experience", []):
        parts.extend(r.get("achievements", []) or [])
        parts.extend(r.get("metrics", []) or [])
        parts.append(str(r.get("scope", "")))
        parts.append(str(r.get("title", "")))
    for p in profile.get("selected_projects", []) or []:
        parts.append(str(p.get("description", "")))
    return " ".join(parts).lower()


def _norm_num(tok: str) -> str:
    return re.sub(r"\s+", "", tok.strip().lower())


def _untraced_numbers(text: str, number_blob: str) -> list[str]:
    """Numeric tokens in `text` not present anywhere in the profile."""
    blob = re.sub(r"\s+", "", number_blob)
    out = []
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group().strip()
        if re.fullmatch(r"\d{1,2}\+?", tok):       # bare small counts — ignore
            continue
        if _norm_num(tok) not in blob:
            out.append(tok)
    return out


_CLASSIFY_SCHEMA = """{
  "claims": [
    {"ref": "<Company>#<n>",
     "label": "traced|jd_adjacent|unverifiable",
     "evidence": "the master_profile fact it rests on, or why it does not"}
  ]
}"""


def _classify_prompt(profile: dict, jd: str, draft: dict) -> str:
    refs = _bullet_refs(draft)
    return "\n".join([
        "Classify each resume bullet against the FACT BASE. Labels:",
        "- traced: the claim restates a fact in the fact base (numbers, "
        "scope, systems, outcomes all present).",
        "- jd_adjacent: the claim reframes a real fact into the JD's "
        "vocabulary — the underlying fact is in the base, only wording is "
        "JD-matched. This is allowed; log it.",
        "- unverifiable: the claim asserts a metric, scope, system, or "
        "outcome NOT supported by the fact base. This is fabrication.",
        "",
        f"FACT BASE:\n{_profile_digest(profile)}",
        "",
        f"JOB DESCRIPTION (for judging 'jd_adjacent'):\n{jd.strip()[:3000]}",
        "",
        "BULLETS:\n" + "\n".join(f'{r["ref"]}: {r["text"]}' for r in refs),
        "",
        f"Return ONLY a JSON object in this shape:\n{_CLASSIFY_SCHEMA}",
    ])


def fabrication_check(draft: dict, profile: dict, jd: str, *,
                      runner: Runner | None = None) -> dict:
    """Hybrid fabrication check -> an output ledger.

    Layer 1 (deterministic): every numeric token in every bullet must appear
    verbatim somewhere in master_profile.json. An untraced number is an
    automatic 'unverifiable'.

    Layer 2 (LLM): a claim-classification pass labels each bullet
    traced / jd_adjacent / unverifiable for the non-numeric content.

    Returns {ledger: [...], unverifiable: [...], counts: {...},
    llm_classified: bool}.
    """
    runner = runner or _run_claude
    number_blob = _profile_number_blob(profile)
    refs = _bullet_refs(draft)

    # Layer 1 — deterministic numeric trace.
    det: dict[str, list[str]] = {}
    for r in refs:
        untraced = _untraced_numbers(r["text"], number_blob)
        if untraced:
            det[r["ref"]] = untraced

    # Layer 2 — LLM claim classification.
    classified: dict[str, dict] = {}
    llm = _extract_json(runner(_classify_prompt(profile, jd, draft)))
    if llm and isinstance(llm.get("claims"), list):
        for c in llm["claims"]:
            if isinstance(c, dict) and c.get("ref"):
                classified[c["ref"]] = c

    ledger: list[dict] = []
    for r in refs:
        ref = r["ref"]
        untraced = det.get(ref, [])
        llm_entry = classified.get(ref, {})
        llm_label = llm_entry.get("label", "")
        # The deterministic check is authoritative for numbers: an untraced
        # number forces 'unverifiable' regardless of what the LLM said.
        if untraced:
            label = "unverifiable"
        elif llm_label in ("traced", "jd_adjacent", "unverifiable"):
            label = llm_label
        else:
            label = "traced"  # no signal either way — treat as traced prose
        ledger.append({
            "ref": ref,
            "company": r["company"],
            "text": r["text"],
            "label": label,
            "untraced_numbers": untraced,
            "evidence": llm_entry.get("evidence", ""),
        })

    unverifiable = [e for e in ledger if e["label"] == "unverifiable"]
    counts = {
        "traced": sum(1 for e in ledger if e["label"] == "traced"),
        "jd_adjacent": sum(1 for e in ledger if e["label"] == "jd_adjacent"),
        "unverifiable": len(unverifiable),
    }
    return {
        "ledger": ledger,
        "unverifiable": unverifiable,
        "counts": counts,
        "llm_classified": bool(classified),
    }


# --------------------------------------------------------------------------
# Stage 3 — Iteration controller
# --------------------------------------------------------------------------

def iterate(profile: dict, jd: str, *,
            max_rounds: int = MAX_ROUNDS,
            runner: Runner | None = None,
            logger: Callable[[dict], None] | None = None) -> dict:
    """Run generate -> critique -> iterate up to `max_rounds` rounds.

    Stops early when the fitment score moves <FITMENT_DELTA_STOP points
    between consecutive rounds. Returns:

      {available, draft, fitment, rounds:[...], ledger, counts, stop_reason}

    `available=False` means the first generation failed (no LLM transport or
    a malformed reply) — the caller should fall back to the deterministic
    renderer.
    """
    runner = runner or _run_claude

    def _log(payload: dict) -> None:
        if logger:
            try:
                logger(payload)
            except Exception:
                pass

    rounds: list[dict] = []
    critique: dict | None = None
    fab: dict | None = None
    best: dict | None = None
    best_fitment = -1
    prev_fitment: int | None = None
    stop_reason = "max_rounds"

    for rnd in range(1, max_rounds + 1):
        draft = generate_draft(profile, jd, critique=critique,
                               fab_findings=fab, runner=runner)
        if not draft:
            if rnd == 1:
                _log({"step": "llm-resume", "round": 1,
                      "decision": "unavailable-fallback-deterministic"})
                return {"available": False, "draft": None, "fitment": None,
                        "rounds": rounds, "ledger": [], "counts": {},
                        "stop_reason": "generation_failed"}
            stop_reason = "generation_failed"
            break

        fab = fabrication_check(draft, profile, jd, runner=runner)
        critique = critique_draft(jd, draft, runner=runner)
        fitment = critique["fitment"] if critique else best_fitment

        rounds.append({
            "round": rnd,
            "fitment": fitment,
            "fab_counts": fab["counts"],
            "n_bullets": len(_bullet_refs(draft)),
        })
        _log({"step": "llm-resume", "round": rnd, "fitment": fitment,
              "fab_counts": fab["counts"]})

        if fitment > best_fitment:
            best, best_fitment = draft, fitment

        if prev_fitment is not None and critique is not None:
            if abs(fitment - prev_fitment) < FITMENT_DELTA_STOP:
                stop_reason = "fitment_converged"
                break
        prev_fitment = fitment

        if critique is None:
            stop_reason = "critique_failed"
            break

    # Final fabrication ledger is computed on the resume that actually ships.
    final_fab = (fabrication_check(best, profile, jd, runner=runner)
                 if best else {"ledger": [], "counts": {}, "unverifiable": []})
    return {
        "available": best is not None,
        "draft": best,
        "fitment": best_fitment if best_fitment >= 0 else None,
        "rounds": rounds,
        "ledger": final_fab["ledger"],
        "counts": final_fab["counts"],
        "stop_reason": stop_reason,
    }


# --------------------------------------------------------------------------
# Output ledger sidecar
# --------------------------------------------------------------------------

def write_ledger(pdf_path: Path, result: dict, candidate: dict) -> Path:
    """Write <resume_stem>.ledger.md next to the PDF. Returns its path."""
    sidecar = pdf_path.parent / (pdf_path.stem + ".ledger.md")
    counts = result.get("counts", {})
    lines = [
        f"# Resume output ledger — {candidate.get('company','?')} / "
        f"{candidate.get('title','?')}",
        "",
        f"Resume: `{pdf_path.name}`",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- **Final fitment (recruiter-callback lens):** "
        f"{result.get('fitment', 'n/a')}/100",
        f"- **Stop reason:** {result.get('stop_reason', '?')}",
        f"- **Iteration rounds:** {len(result.get('rounds', []))}",
        f"- **Claims:** {counts.get('traced',0)} traced, "
        f"{counts.get('jd_adjacent',0)} JD-adjacent restatements, "
        f"{counts.get('unverifiable',0)} unverifiable",
        "",
        "## Per-round fitment",
        "",
    ]
    for r in result.get("rounds", []):
        lines.append(f"- Round {r['round']}: fitment {r['fitment']}, "
                      f"{r['n_bullets']} bullets, "
                      f"fabrication {r['fab_counts']}")
    lines += ["", "## Claim ledger", "",
              "| Bullet | Label | Evidence / note |", "|---|---|---|"]
    for e in result.get("ledger", []):
        note = e.get("evidence", "") or (
            "untraced numbers: " + ", ".join(e["untraced_numbers"])
            if e.get("untraced_numbers") else "")
        text = e["text"][:80] + ("…" if len(e["text"]) > 80 else "")
        lines.append(f"| {e['ref']}: {text} | {e['label']} | {note} |")
    unver = result.get("counts", {}).get("unverifiable", 0)
    lines += ["", "## Honesty note", ""]
    if unver:
        lines.append(f"**{unver} bullet(s) could not be traced** to "
                      "master_profile.json. They were fed back as critique "
                      "across iteration rounds; any that survived are flagged "
                      "above and should be reviewed before sending.")
    else:
        lines.append("Every shipped claim traces to master_profile.json or "
                      "is a JD-adjacent restatement of a real fact.")
    lines += ["", "— generated by agent/llm_resume_generator.py", ""]
    sidecar.write_text("\n".join(lines))
    return sidecar
