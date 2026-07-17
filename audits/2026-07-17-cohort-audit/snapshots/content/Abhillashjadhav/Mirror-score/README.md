# MirrorScore

A daily face-selfie wellness check-in. Upload one photo, get a Glow Score (0–100), a 5-axis radar (skin clarity, hydration, redness, dark circles, freshness), one tiny next action, and a tiered plan from the next hour to the next 30 days.

This repository is the **v0.1 scaffold**: the agent architecture, the orchestration loop, and the eval harness. UI is CLI-only. PWA is v0.2. Full spec in [PRD.md](./PRD.md).

## 60-second pitch

US women, 25–42, are already tracking sleep, cycles, and HRV. The selfie is the missing daily signal they keep eyeballing in the mirror anyway. MirrorScore quantifies it without crossing into medical-advice territory, and ships with a runtime guard (the EvalCritic agent) and a regression harness so prompt changes can't silently regress.

## Architecture in one diagram

```
[selfie] ─► ImageQualityCheck (CV, no LLM)
              │
              ▼
        SkinAnalysisAgent  (vision LLM → 5-axis scores)
              │
              ▼
        RecommendationAgent (text LLM → tiered plan)
              │
              ▼
        EvalCriticAgent     (text LLM → judge: tone, schema, no-med-advice)
              │
              ▼
       MirrorResponse JSON  +  full trace under traces/
```

**3 LLM agents, 1 deterministic preprocessor, 1 orchestrator harness.** Justified in [PRD §5.1](./PRD.md#51-agent-count-3-llm-agents-defended).

## How LLM calls are billed

LLM calls go through [`claude-agent-sdk`](https://pypi.org/project/claude-agent-sdk/), which routes through the local Claude Code CLI session. **No `ANTHROPIC_API_KEY` is set or required** — usage bills against the active Claude Max plan.

For development, CI, and the regression harness, the default is **mock mode**: deterministic stub responses derived from the image hash. Mock mode costs nothing and runs offline. Pass `--live` to flip on real Max-plan calls.

## Install

```bash
pip install -e .
# Generate the synthetic golden-set fixtures (one-time):
python evals/golden_set/make_fixtures.py
```

## Run

One selfie, mock mode (no credit consumed):

```bash
python -m src.cli --image evals/golden_set/case_01.png
```

Same image, live mode (consumes Max plan credits):

```bash
python -m src.cli --image evals/golden_set/case_01.png --live
```

The CLI prints the full `MirrorResponse` JSON to stdout and writes a complete trace to `traces/<timestamp>__<request_id>.json`.

## Regression runs

### Golden set (positive cases)
```bash
python -m evals.regression_run --golden-set evals/golden_set --transport mock   # CI default
python -m evals.regression_run --golden-set evals/golden_set --transport max    # dev (Max plan)
python -m evals.regression_run --golden-set evals/golden_set --transport api    # prod (API key)
```

Iterates the golden cases and reports:
- **Output evals** — schema validity, score ranges, recommendation quality
- **Trajectory evals** — agent invocation order, no-redundant-calls, per-request cost cap
- **Trace evals** — trace file complete, replayable, searchable
- **Golden judge** — score-range and required-axis-citation checks

### Adversarial set (negative cases — must be flagged)
```bash
python -m evals.adversarial_run --transport mock
```

Ten crafted bad responses, each containing a different medical-advice violation class. The EvalCritic must flag 10/10 (TNR=1.0). Exits non-zero on any miss. Required reading: `evals/adversarial/README.md`.

### Trace observability
```bash
python -m src.observability.viewer --status blocked        # recently blocked responses
python -m src.observability.viewer --flagged               # medical_advice_flag=true
python -m src.observability.viewer --show <request_id>     # full trace dump
python -m src.observability.viewer --audit --flagged       # search the audit log
```

### CI
GitHub Actions (`.github/workflows/regression.yml`) runs unit tests + mock golden + mock adversarial on every PR. A separate live job runs against the real Anthropic API when `ANTHROPIC_API_KEY` is configured as a repo secret.

## Tests

```bash
pip install -e '.[dev]'
pytest
```

## Repo layout

```
mirrorscore/
├── PRD.md
├── README.md
├── pyproject.toml
├── src/
│   ├── cli.py
│   ├── agents/
│   │   ├── image_quality.py        # deterministic CV preprocessor
│   │   ├── skin_analysis.py        # vision LLM agent
│   │   ├── recommendation.py       # text LLM agent
│   │   ├── eval_agent.py           # runtime judge
│   │   └── prompts/                # version-controlled .md prompts
│   ├── orchestration/
│   │   ├── react_loop.py           # the orchestrator
│   │   ├── claude_client.py        # claude-agent-sdk transport (+ mock)
│   │   ├── cost_tracker.py
│   │   └── tracer.py
│   └── schemas/                    # Pydantic contracts
├── evals/
│   ├── golden_set/                 # 5 synthetic fixtures + manifest
│   ├── output_evals.py
│   ├── trajectory_evals.py
│   ├── trace_evals.py
│   ├── llm_judge.py
│   └── regression_run.py
├── traces/                         # one JSON per request (gitignored)
└── tests/
```

## What's deferred to v0.2

- PWA / mobile UI (Next.js 14 + Supabase + Stripe, $9/mo, 7-day trial — design locked, build pending)
- Auth, history, day-over-day trends
- Push / scheduling (LaunchAgent, cron)
- Real-photo golden set — manifest schema and contributor flow are ready; see `evals/golden_set/PHOTOS.md`
- Face-detection layer in `image_quality.py` (out-of-band model dep deferred)

## Adding real photos to the golden set

See `evals/golden_set/PHOTOS.md` for the per-photo checklist (source, license, EXIF strip, manifest entry, human labels). Drop photos in, append manifest entries, re-run regression.

## Phase 2 — generative 30-day projection (deferred)

The original concept includes generating an image of the user's projected skin state at 30 days under the recommended plan. This is **deferred from v0.1 and is not designed in this scaffold beyond a nullable `projection_30d` field reserved in the response schema**.

We are deferring it because it is fundamentally a **validation problem, not an engineering problem**: we cannot accurately predict what a real human face will look like in 30 days under a wellness plan, and showing a user a hopeful projection that does not materialize is worse than showing nothing — it is trust-destroying and arguably a deceptive practice under FTC §5. Phase 2 needs a longitudinal paired-selfie dataset, a calibrated perceptual-similarity metric for "predicted vs actual skin state at T+30d," a refusal threshold below which we do not generate, and an "illustrative not predictive" UI treatment regardless of confidence — its own eval design before any code ships. The schema reservation is the only Phase 2 artifact in this scaffold.

## Compliance posture

MirrorScore is a wellness reflection tool, not a medical device. The EvalCritic enforces a hard blocklist of medical-advice terms at runtime and the response always carries the standard disclaimer. Full posture and disclaimer text in [PRD §8](./PRD.md#8-compliance-safety-disclaimers).
