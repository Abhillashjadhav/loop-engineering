"""Autonomous candidate scorer.

Default mode: heuristic rubric (Domain 30 / Seniority 20 / Location 10 /
Tech 15 / Mgmt 10 / Comp 15) with Step 4b adjacent-skill bumps.

Optional Claude API mode (when ANTHROPIC_API_KEY is set): uses Claude
to apply judgment-based scoring for higher fidelity. Falls back to
heuristic on any API failure.

Usage:
    from agent.scorer import score_candidates
    scored = score_candidates(filtered_candidates, profile)
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import threading
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-opus-4-7"

# Apply gate = 80 (Hard Rule 1). Only roles at 80+ — by original score OR by a
# bumped score — get a tailored resume and go into the "apply" set. The 60–79
# band is the near-miss band: it is run through the Step 4b adjacency bump and,
# when a *genuine* documented adjacency lifts it to 80+, it is promoted to a
# bumped fit. A 60–79 role with no real adjacency stays a near-miss (gap analysis
# only, no resume). The floor is never cleared by inflation — only by a real,
# traceable adjacent-skill match (per the user 2026-06-18: "if it's 60–79 and the
# profile genuinely supports it, bump it above 80 and apply only to those").
FIT_THRESHOLD = 80
NEAR_MISS_FLOOR = 60

# Step 4b adjacency cap. Raised 15 → 20 so the *entire* 60–79 near-miss band can
# reach the 80 floor when adjacency is genuine (a 60 needs +20). The bump is the
# SUM of matched, documented adjacency signals (each ties to a real
# master_profile.json bullet) capped here — so a role matching several of
# Abhillash's real strengths bumps more than one matching a single weak adjacency,
# and a role matching none does not bump at all. The cap, not inflation, is what
# keeps this honest: no signal → no bump → stays a near-miss.
BUMP_CAP = 20


# ---------- Heuristic rubric (always available, no network) ----------

def _domain_match(title: str, desc: str) -> tuple[int, list[str]]:
    """Score 0-30 based on JD content alignment.

    Every legitimate PM role gets a baseline 10 (any role with "product manager"
    in the title is at minimum adjacent to Abhillash's experience — the resume
    tailor will reframe per JD). Domain-specific signals stack on top.
    """
    d = (desc or "").lower()
    t = (title or "").lower()
    score = 0
    signals = []

    # Baseline — every real PM role counts. The previous 0 floor was the main
    # reason Conga/OneTrust/Docusign Principal PM roles scored 46.
    if 'product' in t or 'pm' in t.split():
        score += 10
        signals.append('baseline-pm')

    if any(k in d for k in ['agentic', 'genai', 'gen ai', 'generative ai', 'llm', 'rag', 'multi-llm', 'langchain']):
        score += 12; signals.append('genai/agentic')
    elif any(k in d for k in ['ai/ml', 'machine learning', 'artificial intelligence', 'ai-driven', 'ai-powered']):
        score += 8; signals.append('ai/ml')

    if any(k in d for k in ['observability', 'developer platform', 'developer velocity',
                             'developer productivity', 'eval framework', 'drift monitoring']):
        score += 10; signals.append('platform/observability')
    elif 'platform' in d and ('product' in d or 'engineer' in d or 'api' in d):
        score += 6; signals.append('generic-platform')

    if any(k in d for k in ['b2b saas', 'b2b marketplace', 'multi-tenant', 'enterprise saas']):
        score += 6; signals.append('b2b-saas')
    elif 'enterprise' in d and ('saas' in d or 'software' in d):
        score += 4; signals.append('enterprise')

    if any(k in d for k in ['subscription', 'recurring revenue', 'arr', 'pricing strategy']):
        score += 4; signals.append('subscriptions')

    if any(k in d for k in ['payment', 'fintech', 'bnpl', 'psp', 'cross-border']):
        score += 5; signals.append('payments')

    if any(k in d for k in ['recommendation', 'personalization', 'personalisation', 'discovery',
                             'search', 'ranking']):
        score += 4; signals.append('reco/personalization')

    if 'api' in d and ('microservice' in d or 'developer' in d or 'platform' in d or 'sdk' in d):
        score += 3; signals.append('api')

    # Governance / Trust & Safety — Wayfair Model Proxy overlap
    if any(k in d for k in ['governance', 'trust and safety', 'compliance', 'risk', 'audit']):
        score += 3; signals.append('governance')

    return min(30, score), signals


def _seniority_score(title: str) -> tuple[int, str]:
    t = (title or "").lower()
    if any(k in t for k in ['vp ', 'vice president', 'sr. director', 'senior director', 'sr director']):
        return 20, 'vp/sr-dir'
    if 'director' in t: return 18, 'director'
    if any(k in t for k in ['principal', 'head of', 'gpm', 'group product']): return 17, 'principal/head'
    if 'senior staff' in t: return 17, 'sr-staff'
    if 'staff' in t: return 14, 'staff'
    if 'lead product' in t: return 13, 'lead'
    if any(k in t for k in ['senior product', 'sr. product', 'sr product']): return 11, 'senior-pm'
    if 'senior manager' in t: return 11, 'sr-mgr'
    return 7, 'other'


def _location_score(loc: str) -> tuple[int, str]:
    l = (loc or "").lower()
    if 'remote' in l: return 10, 'remote'
    if 'bengaluru' in l or 'bangalore' in l: return 10, 'bengaluru'
    if 'mumbai' in l: return 9, 'mumbai'
    if 'hyderabad' in l: return 9, 'hyderabad'
    # Tier-2 Indian metros — raised from 4-5 → 7-8 so a strong role in
    # Pune/NCR/Chennai is not silently penalized below threshold.
    if 'pune' in l: return 8, 'pune'
    if any(k in l for k in ['gurgaon', 'gurugram', 'delhi', 'noida', 'ncr']): return 7, 'ncr'
    if 'chennai' in l: return 8, 'chennai'
    if l.strip() == 'india' or 'india' in l: return 7, 'india-generic'
    return 2, 'other'


def _tech_score(desc: str) -> int:
    d = (desc or "").lower()
    keys = ['llm', 'rag', 'aws', 'kubernetes', 'microservices', 'agentic', 'langchain',
            'python', 'sql', 'kafka', 'grafana', 'observability', 'docker', 'postgres',
            'mongodb', 'tensorflow', 'pytorch', 'spark', 'snowflake']
    return min(15, sum(k in d for k in keys) * 2)


def _mgmt_score(title: str) -> int:
    t = (title or "").lower()
    if any(k in t for k in ['director', 'vp ', 'vice president', 'head of',
                             'sr. director', 'senior director', 'group product',
                             'senior manager']):
        return 10
    if any(k in t for k in ['senior staff', 'principal', 'staff']): return 7
    if 'lead' in t: return 8
    return 5


def _comp_score(title: str) -> int:
    t = (title or "").lower()
    if any(k in t for k in ['vp ', 'sr. director', 'senior director', 'head of']): return 14
    if any(k in t for k in ['director', 'principal', 'group', 'senior staff']): return 12
    if any(k in t for k in ['staff', 'lead product']): return 10
    if 'senior' in t: return 9
    return 7


def heuristic_score(c: dict) -> dict:
    title = c.get('title', '')
    desc = c.get('description_excerpt', '') or c.get('description', '')
    loc = c.get('location', '')

    dom, sigs = _domain_match(title, desc)
    sen, sen_label = _seniority_score(title)
    locs, loc_label = _location_score(loc)
    tech = _tech_score(desc)
    mgmt = _mgmt_score(title)
    comp = _comp_score(title)
    total = dom + sen + locs + tech + mgmt + comp

    # Step 4b adjacency bumps — applied only when total is in the 60-79 near-miss
    # band AND a genuine, documented adjacency exists. Each matched signal adds its
    # weight (the bumps STACK — multiple real adjacencies = stronger case), then the
    # sum is capped at BUMP_CAP so the full band can reach the 80 floor without ever
    # being inflated past what real evidence supports. No signal → bump stays 0 →
    # the role remains a near-miss. The agentic/GenAI signal is Abhillash's *current*
    # Wayfair Model Proxy job (near-direct overlap, not mere adjacency) so it carries
    # the heaviest single weight.
    #
    # IMPORTANT: bump keywords must be SPECIFIC compound phrases — bare 'platform'
    # appears in virtually every senior PM JD and would inflate ~109 generic roles
    # to "fit" (run #60 failure). Only specific platform types qualify.
    bump = 0
    bump_reasons = []
    if NEAR_MISS_FLOOR <= total < FIT_THRESHOLD:
        t_low = title.lower()
        d_low = desc.lower()
        if any(k in t_low for k in ['agentic', 'genai', 'gen ai', 'llm']) or \
           any(k in d_low for k in ['agentic', 'genai', 'gen ai', 'llm', 'rag', 'multi-llm']):
            bump += 14
            bump_reasons.append('Wayfair Model Proxy agentic/GenAI platform — near-direct overlap')
        if any(k in (t_low + ' ' + d_low) for k in ['observability', 'developer productivity',
                                                      'developer platform', 'ml platform',
                                                      'ai platform', 'genai platform',
                                                      'data platform', 'platform engineering']):
            bump += 10
            bump_reasons.append('Wayfair GenAI dev platform 2,800+ engineers $300M impact')
        if any(k in (t_low + ' ' + d_low) for k in ['recommendation', 'personalization', 'personalisation']):
            bump += 10
            bump_reasons.append('Amazon AI/ML reco $1.2B + CTL personalization $3.2B GMV')
        if 'b2b' in t_low or 'b2b' in d_low or 'subscription' in d_low:
            bump += 8
            bump_reasons.append('PayTM B2B founding PM + IndiaMART subscriptions ₹30 Cr ARR')
        if any(k in t_low for k in ['payment', 'bnpl', 'fraud', 'risk', 'fintech']):
            bump += 8
            bump_reasons.append('PayTM B2B Payments founding PM (0-to-1 fintech)')
        bump = min(bump, BUMP_CAP)

    bumped_total = min(95, total + bump)
    bumped = bump > 0 and bumped_total >= FIT_THRESHOLD and total < FIT_THRESHOLD

    if total >= FIT_THRESHOLD:
        disp = 'fit'
    elif bumped_total >= FIT_THRESHOLD:
        disp = 'bumped_fit'
    elif total >= NEAR_MISS_FLOOR:
        disp = 'near_miss'
    else:
        disp = 'silent_drop'

    return {
        **c,
        'score': total,
        'bumped_score': bumped_total,
        'bumped': bumped,
        'bump_reasons': bump_reasons,
        'disposition': disp,
        'rubric': {
            'domain_30': dom, 'domain_signals': sigs,
            'seniority_20': sen, 'seniority_label': sen_label,
            'location_10': locs, 'location_label': loc_label,
            'tech_15': tech, 'mgmt_10': mgmt, 'comp_15': comp,
        },
        'scored_via': 'heuristic',
    }


def _claude_cli_score_one(c: dict, profile_summary: str,
                           react_logger=None, tracer=None) -> dict | None:
    """Score one candidate via the `claude` CLI (uses Max-plan OAuth quota).

    This is the preferred path: it consumes the user's Claude Max subscription
    via CLAUDE_CODE_OAUTH_TOKEN rather than billing ANTHROPIC_API_KEY by token.
    Returns None on failure so the caller can fall back to the heuristic.

    The CLI is invoked as `claude -p <prompt> --output-format json --max-turns 1`.
    `--output-format json` returns a JSON envelope `{type, ..., result}` where
    `result` is the assistant's final text. We extract the JSON rubric from
    `result` exactly the same way as the API path.
    """
    import shutil
    import subprocess
    if shutil.which("claude") is None:
        return None
    desc = (c.get('description_excerpt', '') or c.get('description', ''))[:2500]
    jd_source = c.get('jd_source') or (
        'actual' if desc else 'title_only'
    )
    prompt = (
        f"Score this job opening for Abhillash Jadhav per the daily-agent rubric. "
        f"PROFILE: {profile_summary}\n\n"
        f"JOB:\nCompany: {c.get('company','?')}\nTitle: {c.get('title','?')}\n"
        f"Location: {c.get('location','?')}\nJD source: {jd_source}\n"
        f"Description (truncated): {desc}\n\n"
        f"RUBRIC (return integers, total <= 95):\n"
        f"- domain_30: domain match to AI/ML/GenAI/Platform/B2B-SaaS PM (0-30). "
        f"Baseline 10 ONLY for roles explicitly involving AI/ML/GenAI/LLM/developer-platform "
        f"work; 0 baseline for generic PM roles without these signals.\n"
        f"- seniority_20: title and scope match Director/Principal/GPM target (0-20). "
        f"Senior/Staff/Lead PM = 11-13. Director/Principal = 17-18. VP = 20.\n"
        f"- location_10: Remote/Bengaluru/Mumbai/Hyderabad full; Pune/Chennai=8; NCR=7.\n"
        f"- tech_15: LLM/RAG/AWS/microservices/agentic/observability overlap (0-15). "
        f"Generic 'platform' or 'product' without specific tech stack = 0-2.\n"
        f"- mgmt_10: people-mgmt fit (0-10).\n"
        f"- comp_15: comp signal from seniority (0-15).\n"
        f"- adjacency_bump_0_20: Step 4b uplift (0-{BUMP_CAP}) ONLY if total is in "
        f"{NEAR_MISS_FLOOR}-{FIT_THRESHOLD-1} AND a SPECIFIC documented adjacency applies "
        f"(Wayfair GenAI platform, Amazon reco engine, PayTM B2B payments — not generic "
        f"'platform' or 'product management'). 0 if no specific adjacency. Never inflate "
        f"to clear the {FIT_THRESHOLD} floor.\n"
        f"- bump_reasons: list tying bump to specific Abhillash bullets.\n"
        f"- disposition: fit/bumped_fit/near_miss/silent_drop.\n\n"
        f"CALIBRATION: A typical day produces 1-10 genuine fits. If you find yourself "
        f"scoring more than 15 roles as 80+, recalibrate — you are being too generous.\n\n"
        f"Return ONLY a JSON object, no prose:\n"
        f'{{"domain_30":int,"seniority_20":int,"location_10":int,"tech_15":int,'
        f'"mgmt_10":int,"comp_15":int,"adjacency_bump_0_20":int,'
        f'"bump_reasons":[str],"disposition":str}}'
    )
    if react_logger:
        react_logger({"step": "3-score", "company": c.get("company"),
                      "intent": "score via claude CLI", "jd_source": jd_source})
    span_cm = tracer.span("claude_cli", name=f"score {c.get('company','?')}",
                           model="claude-opus-4-7",
                           input_data={"prompt": prompt[:4000],
                                        "company": c.get("company"),
                                        "jd_source": jd_source}) if tracer else None
    span = span_cm.__enter__() if span_cm else None
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--model", "claude-opus-4-7",
             "--output-format", "json",
             "--max-turns", "20",
             "--disallowed-tools", "Bash,Edit,Write,WebFetch,WebSearch,Read"],
            capture_output=True, text=True, timeout=90,
            env={**os.environ},
        )
        if span:
            span.set_output({"stdout": proc.stdout[:4000], "rc": proc.returncode})
            try:
                from agent.tracing import approx_tokens
                span.set_tokens(input=approx_tokens(prompt),
                                 output=approx_tokens(proc.stdout))
            except Exception:
                pass
        if proc.returncode != 0:
            if react_logger:
                react_logger({"step": "3-score", "company": c.get("company"),
                              "observation": f"CLI rc={proc.returncode}",
                              "decision": "fallback-heuristic",
                              "stderr": proc.stderr[-300:]})
            return None
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result") or ""
        m = re.search(r'\{[\s\S]*\}', result_text)
        if not m:
            if react_logger:
                react_logger({"step": "3-score", "company": c.get("company"),
                              "observation": "no json in response",
                              "decision": "fallback-heuristic"})
            return None
        rubric = json.loads(m.group())
        total = sum(rubric[k] for k in ('domain_30', 'seniority_20', 'location_10',
                                         'tech_15', 'mgmt_10', 'comp_15'))
        bump = rubric.get('adjacency_bump_0_20',
                          rubric.get('adjacency_bump_0_12', 0)) or 0
        bump = min(max(int(bump), 0), BUMP_CAP)
        bumped_total = min(95, total + bump)
        bumped = bump > 0 and bumped_total >= FIT_THRESHOLD and total < FIT_THRESHOLD
        if total >= FIT_THRESHOLD:
            disp = 'fit'
        elif bumped_total >= FIT_THRESHOLD:
            disp = 'bumped_fit'
        elif total >= NEAR_MISS_FLOOR:
            disp = 'near_miss'
        else:
            disp = 'silent_drop'
        if react_logger:
            react_logger({"step": "3-score", "company": c.get("company"),
                          "observation": f"total={total} bump={bump} disp={disp}",
                          "decision": disp, "rubric": rubric,
                          "scored_via": "claude_cli"})
        return {
            **c,
            'score': total,
            'bumped_score': bumped_total,
            'bumped': bumped,
            'bump_reasons': rubric.get('bump_reasons', []),
            'disposition': disp,
            'rubric': {k: rubric[k] for k in ('domain_30', 'seniority_20', 'location_10',
                                                'tech_15', 'mgmt_10', 'comp_15')},
            'scored_via': 'claude_cli',
            'jd_source': jd_source,
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ValueError) as e:
        if react_logger:
            react_logger({"step": "3-score", "company": c.get("company"),
                          "observation": f"exception: {type(e).__name__}",
                          "decision": "fallback-heuristic"})
        if span:
            span.set_error(f"{type(e).__name__}: {e}")
        return None
    finally:
        if span_cm:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:
                pass


# ---------- Optional Claude API mode (judgment-based) ----------

def _claude_score_one(c: dict, profile_summary: str) -> dict | None:
    """Score one candidate via Claude. Returns None on failure."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key or requests is None:
        return None
    desc = (c.get('description_excerpt', '') or c.get('description', ''))[:2500]
    prompt = f"""Score this job opening for Abhillash Jadhav per the daily-agent rubric.

PROFILE SUMMARY:
{profile_summary}

JOB:
Company: {c.get('company','?')}
Title: {c.get('title','?')}
Location: {c.get('location','?')}
Description (truncated): {desc}

RUBRIC (return integers, total <= 95):
- domain_30: domain match to AI/ML/GenAI/Platform/B2B-SaaS PM (0-30). Baseline
  10 ONLY for roles explicitly involving AI/ML/GenAI/LLM/developer-platform work;
  0 baseline for generic PM roles without these signals.
- seniority_20: title and scope match Director/Principal/GPM target (0-20).
  Senior/Staff/Lead PM = 11-13. Director/Principal = 17-18. VP = 20.
- location_10: Remote/Bengaluru/Mumbai/Hyderabad full credit (0-10);
  Pune/Chennai = 8; NCR = 7; India-generic = 7.
- tech_15: LLM/RAG/AWS/microservices/agentic/observability overlap (0-15).
  Generic 'platform' or 'product' without specific tech stack = 0-2.
- mgmt_10: people-mgmt vs IC fit (0-10)
- comp_15: comp signal from title seniority (0-15)
- adjacency_bump_0_{BUMP_CAP}: Step 4b adjacency uplift (0-{BUMP_CAP}) if total in {NEAR_MISS_FLOOR}-{FIT_THRESHOLD - 1} band
  AND a SPECIFIC documented adjacency applies (Wayfair GenAI platform, Amazon reco engine, PayTM B2B payments —
  not generic 'platform' or 'product management'). 0 if no specific adjacency.
  Never inflate purely to clear the {FIT_THRESHOLD} floor.
- bump_reasons: list of strings tying bump to specific master_profile bullets
- disposition: "fit" if total>={FIT_THRESHOLD}, "bumped_fit" if total<{FIT_THRESHOLD} and total+bump>={FIT_THRESHOLD},
               "near_miss" if {NEAR_MISS_FLOOR}<=total<{FIT_THRESHOLD}, "silent_drop" if total<{NEAR_MISS_FLOOR}

CALIBRATION: A typical day produces 1-10 genuine fits. If you find yourself scoring
more than 15 roles as 80+, recalibrate — you are being too generous.

Return ONLY a JSON object (no prose):
{{"domain_30": int, "seniority_20": int, "location_10": int, "tech_15": int,
  "mgmt_10": int, "comp_15": int, "adjacency_bump_0_{BUMP_CAP}": int,
  "bump_reasons": [str], "disposition": str}}
"""
    try:
        resp = requests.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return None
        rubric = json.loads(m.group())
        total = sum(rubric[k] for k in ('domain_30', 'seniority_20', 'location_10',
                                         'tech_15', 'mgmt_10', 'comp_15'))
        bump = rubric.get('adjacency_bump_0_20',
                          rubric.get('adjacency_bump_0_12', 0)) or 0
        bump = min(max(int(bump), 0), BUMP_CAP)
        bumped_total = min(95, total + bump)
        bumped = bump > 0 and bumped_total >= FIT_THRESHOLD and total < FIT_THRESHOLD
        # Re-derive disposition with current thresholds, ignoring whatever the
        # LLM emitted — keeps a single source of truth.
        if total >= FIT_THRESHOLD:
            disp = 'fit'
        elif bumped_total >= FIT_THRESHOLD:
            disp = 'bumped_fit'
        elif total >= NEAR_MISS_FLOOR:
            disp = 'near_miss'
        else:
            disp = 'silent_drop'
        return {
            **c,
            'score': total,
            'bumped_score': bumped_total,
            'bumped': bumped,
            'bump_reasons': rubric.get('bump_reasons', []),
            'disposition': disp,
            'rubric': {k: rubric[k] for k in ('domain_30', 'seniority_20', 'location_10',
                                                'tech_15', 'mgmt_10', 'comp_15')},
            'scored_via': 'claude',
        }
    except Exception as e:  # noqa: BLE001
        sys_err = sys = __import__('sys')
        print(f"[scorer] Claude scoring failed for {c.get('company','?')}: {e}", file=sys_err.stderr)
        return None


def score_candidates(candidates: list[dict], profile: dict,
                     react_logger=None, tracer=None) -> list[dict]:
    """Score every candidate. Order of preference:

    1. `claude` CLI (uses Max-plan OAuth via CLAUDE_CODE_OAUTH_TOKEN) — $0
       on top of the Max subscription, judgment-based.
    2. ANTHROPIC_API_KEY API (legacy paid path).
    3. Heuristic rubric (always available, no network).

    `react_logger`, when provided, is called with one dict per per-role step
    so the orchestrator can append to trajectory.jsonl per CLAUDE.md Step 0.
    Every returned candidate carries `scored_via` ∈ {"claude_cli", "claude",
    "heuristic"} and `jd_source` ∈ {"actual", "title_only"} so the brief is
    transparent about which scores you can trust.
    """
    summary_lines = [
        f"- 11+ years senior product management",
        f"- Currently Senior Manager, GenAI Product Management at Wayfair (Wayfair Model Proxy, 2,800+ engineers, $300M impact, $15M cost reduction)",
        f"- Prior Director PM at CTL Cimpress ($3.2B GMV personalization platform across 13 brands)",
        f"- Prior Senior PM at Amazon (Promotions Platform $4B GMV, AI/ML reco engine $1.2B annualised, CDP across 800M+ customers)",
        f"- Founding PM leader at PayTM B2B Payments (0-to-1 fintech)",
        f"- Prior VP Product at IndiaMART (subscriptions ₹30 Cr ARR)",
        f"- Target band: Director / Principal / GPM / VP Product",
        f"- Preferred locations: Remote, Bengaluru, Mumbai, Hyderabad",
    ]
    profile_summary = "\n".join(summary_lines)

    has_cli = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip() != ""
    has_api = bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())

    def _heuristic_with_jd_source(c: dict) -> dict:
        scored = heuristic_score(c)
        if 'jd_source' not in scored:
            scored['jd_source'] = ('actual' if (c.get('description_excerpt') or '').strip()
                                   else 'title_only')
        return scored

    # No LLM available → pure heuristic; fast, keep it simple and serial.
    if not has_cli and not has_api:
        return [_heuristic_with_jd_source(c) for c in candidates]

    # LLM scoring is a blocking subprocess / HTTP call per candidate (up to 90s
    # each). Done serially over ~290 candidates it cannot finish inside the CI
    # budget — run #27765752429 was force-cancelled at the 60-min cap mid-call.
    # Fan the per-candidate calls out across a thread pool (I/O-bound, so threads
    # are the right tool). Standing policy (user, 2026-06-18): never process a
    # divisible, I/O-bound workload serially — default to >= 10 parallel lanes.
    # Workers default to 10, override via SCORER_MAX_WORKERS (clamped 1..16).
    # Per-candidate failures still fall back to heuristic, so a worker that hits
    # a rate limit just degrades that one row instead of failing the run.
    log_lock = threading.Lock()

    def _safe_log(rec: dict) -> None:
        if react_logger:
            with log_lock:               # serialize trajectory.jsonl appends
                react_logger(rec)

    def _score_one(c: dict) -> dict:
        scored = None
        if has_cli:
            scored = _claude_cli_score_one(c, profile_summary,
                                            react_logger=_safe_log, tracer=tracer)
        if scored is None and has_api:
            scored = _claude_score_one(c, profile_summary)
        if scored is None:
            _safe_log({"step": "3-score", "company": c.get("company"),
                       "decision": "heuristic-fallback"})
            scored = _heuristic_with_jd_source(c)
        return scored

    try:
        max_workers = int(os.environ.get("SCORER_MAX_WORKERS", "10") or "10")
    except ValueError:
        max_workers = 10
    max_workers = max(1, min(max_workers, 16))

    out: list[dict | None] = [None] * len(candidates)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(_score_one, c): i for i, c in enumerate(candidates)}
        for fut in concurrent.futures.as_completed(fut_to_idx):
            i = fut_to_idx[fut]
            try:
                out[i] = fut.result()
            except Exception:            # never let one bad candidate sink the batch
                out[i] = _heuristic_with_jd_source(candidates[i])
    return [s for s in out if s is not None]


if __name__ == "__main__":  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    cands = [json.loads(l) for l in open(args.input)]
    profile = json.load(open(args.profile))
    scored = score_candidates(cands, profile)
    json.dump(scored, open(args.output, 'w'), indent=2, ensure_ascii=False)
    from collections import Counter
    print({k: v for k, v in Counter(c['disposition'] for c in scored).items()})
