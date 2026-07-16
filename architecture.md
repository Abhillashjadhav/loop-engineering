# Architecture — Daily Job Search Agent

## Goal
Every morning at 08:30 IST, autonomously surface 1–3 high-fit Director PM /
Principal PM / GPM roles for Abhillash Jadhav across India + Remote, generate
tailored resumes for ≥85% fits, and email the brief — all without opening a
laptop, running on Anthropic's cloud infrastructure (Claude Code Routine).

## High-level data flow
1. **Sources** — ATS APIs (Greenhouse, Lever, Ashby) for ~100+ tracked companies,
   plus Indeed MCP (India only), plus Gmail label for LinkedIn/Naukri/Hirist alerts.
2. **Rule filter** — Python-only, $0 in tokens. Drops 70–80% of raw candidates
   via title regex, location whitelist, decline list, and seen-in-last-14-days hash.
3. **Score** — Claude scores survivors against `master_profile.json` using a
   weighted rubric (domain 30 / seniority 20 / location 10 / tech 15 / people-mgmt 10 / comp 15).
4. **Branch by score**:
   - ≥85% → generate tailored resume + ATS readiness report
   - 70–84% → include in digest with gap analysis (no resume)
   - <70% → drop silently
5. **Deliver** — Gmail digest with PDFs attached + JSON brief committed to GitHub repo
   (which is also wired into Claude project knowledge for follow-up chats).

## Why this architecture
- **MCP-first, API-fallback.** ATS APIs are free, structured, and authoritative.
  Indeed MCP handles the long tail. Gmail-piped alerts capture LinkedIn without scraping.
- **Rules before LLM.** Most JDs can be rejected for $0 by Python rules. This cuts
  token cost ~70%.
- **Hybrid model strategy.** Default to Sonnet; escalate to Opus only for resume
  generation. Haiku could also be used for first-pass scoring at higher volume.
- **Honesty rails.** Hard 85% floor for resume generation. No metric inflation,
  no fabrication. Strategic reframing only. Enforced in `CLAUDE.md`.
- **Trajectory logging.** Every tool call appended to `outputs/YYYY-MM-DD/trajectory.jsonl`
  for evaluation.

## File map
```
job-agent/
├── architecture.md            ← this file
├── README.md                  ← getting-started guide
├── CLAUDE.md                  ← agent prompt (the brain)
├── profile/
│   ├── master_profile.json    ← career data (single source of truth)
│   ├── target_companies.yaml  ← 100+ companies with ATS slugs
│   ├── decline_list.txt       ← skip these companies/roles
│   └── referral_network.csv   ← referral contacts for outreach
├── templates/                 ← resume HTML/JSON templates
├── agent/
│   ├── sources/
│   │   ├── greenhouse.py      ← Greenhouse boards-api client
│   │   ├── lever.py           ← Lever postings client
│   │   ├── ashby.py           ← Ashby job-board client
│   │   └── fetch_all.py       ← orchestrator: hits all sources, merges output
│   ├── rule_filter.py         ← Python-only filtering (title/location/dedupe)
│   ├── ats_report.py          ← parseability + keyword coverage scorer
│   └── notifier.py            ← Gmail digest formatter
├── eval/
│   ├── judge_prompt.md        ← LLM-as-judge for trajectory + output
│   └── eval_results/          ← daily eval JSON
├── outputs/
│   └── YYYY-MM-DD/
│       ├── candidates.json    ← all scored candidates
│       ├── brief.md           ← human-readable brief (also flows to Claude project)
│       ├── trajectory.jsonl   ← tool-call trace for evaluation
│       └── resumes/*.pdf      ← tailored PDFs for ≥85% fits
└── .github/workflows/         ← GitHub Actions YAML (Path B fallback only)
```

## Token budget per run (estimated)
| Phase | Tokens (input + output) |
|---|---|
| Source fetch (Python only) | 0 |
| Rule filter (Python only) | 0 |
| Profile cache write (one-time) | ~5K |
| Profile cache hits (every JD scoring) | ~500/JD |
| JD scoring (5–8 survivors) | ~30K total |
| Resume generation (1–3 fits) | ~80–200K |
| Digest composition | ~10K |
| **Total per daily run** | **~150–250K tokens** |

On Max 20x ($200/mo), this is comfortably within budget — well under 5% of weekly quota.

## What runs where
| Component | Runtime | Cost |
|---|---|---|
| Claude Code Routine | Anthropic cloud | Included in Max plan |
| Python source modules | Inside Routine container | $0 |
| MCP tools (Indeed, Gmail, Drive) | Anthropic-hosted | Included |
| GitHub repo | GitHub free tier | $0 (private repo) |

No servers to manage. No cron job to babysit. No surprise API bills.
