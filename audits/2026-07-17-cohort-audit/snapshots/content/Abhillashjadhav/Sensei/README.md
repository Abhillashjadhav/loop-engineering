# Reply Sensei

Reply-drafter for ESL professionals navigating US/Western workplace hierarchy. Produces 2–3 reply variants with tone label, hierarchy calibration, teaching-layer explanation, and risk note per variant.

## Quickstart (60 seconds)

```bash
git clone <this repo>
cd sensei
./run.sh   # creates venv, installs, starts server, opens browser
```

The app opens at <http://localhost:8765>. Type a message you received, pick a relationship, pick a goal, hit "Draft replies." Done.

> **Auth:** uses your local Claude Code CLI session — billed against your Max plan, no API key.

## Live (read-only) — GitHub Pages

Once Pages is enabled on this repo, the static viewer with the 4 golden-case traces is at:

```
https://abhillashjadhav.github.io/sensei/
```

To enable (one-time, takes 30s): repo → Settings → Pages → **Source: GitHub Actions**. The workflow in `.github/workflows/pages.yml` deploys on every push to `main` or `claude/hold-on-sensei-JNGiv`.

The interactive `/draft` form must run locally — Max-plan auth binds to your local Claude Code session and can't be hosted remotely without re-introducing API keys.

## Status

v0.1 scaffold — CLI + JSON output + interactive web app + static viewer. See [`PRD.md`](./PRD.md) for product spec, agent-count justification, and eval-first design rationale.

## Install

```bash
pip install -e .
```

**Auth: no API key needed.** LLM calls route through the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/), which uses the local Claude Code session. Calls consume your **Claude Code Max plan** quota, not API console credits. Make sure `claude` (the CLI) is installed and logged in on the host running Reply Sensei.

## Usage

### One-line run

```bash
./run.sh
```

This creates `.venv`, installs deps, starts the server on <http://localhost:8765>, and opens your browser. Requires the Claude Code CLI logged into your Max plan (the SDK uses it for auth — no API key needed).

Or manually:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m src.server
```

Two tabs in the app:
- **Draft a reply** — form (message + relationship chip + goal chip) → live `/draft` against the 3-agent pipeline. Shows the parsed context, 3 variants, eval verdict, and trajectory inline.
- **Browse examples** — the 5 golden-case regression traces, same renderer.

### CLI

```bash
python -m src.cli \
  --message "Hey, any chance you could pick up the Q3 deck by Friday?" \
  --relationship manager \
  --goal push-back
```

Returns JSON with 2–3 variants, each tagged with `tone_label`, `text`, `why_it_works`, `risk_if_misapplied`, plus the EvalAgent verdict.

## Regression run

```bash
python -m evals.regression_run
```

Loads the 5 golden-set examples in `evals/golden_set/`, runs the full pipeline, and reports per-case pass/fail with rubric scores.

## Orchestration: two modes

Reply Sensei ships with two orchestrators. Both route every LLM call through the Claude Agent SDK on your Max plan — no API key, no per-call dollar cost.

| Mode | Trajectory | Calls/request | When |
|---|---|---|---|
| **Pipeline** (default) | Deterministic: Context → Reply → Eval, fixed order, with a 1-shot eval-driven retry | 3 (4 on retry) | Fast, lean on tokens, predictable. The everyday path. |
| **ReAct** (`--react`) | Genuine: an LLM orchestrator reasons about state and chooses each next action (parse_context / generate_replies / evaluate / finish) | ~7 (one orchestrator reasoning call per step) | When you want true model-driven control flow. More tokens, still $0 on Max plan. |

```bash
python -m src.cli --react --message "..." --relationship manager --goal push-back
# or in the web app: POST /draft/stream {"mode": "react"}
```

The default pipeline is **agentic-lite**: multi-agent + an independent critic loop, but a scripted trajectory. The `--react` mode is a **genuine ReAct loop** — the orchestrator's `thought`/`action` at each step is model-generated, and it can skip, reorder, or retry based on what it observes. Verified live: the orchestrator chose `parse_context → generate_replies → evaluate → finish` by reasoning about `has_context`/`has_variants`/`last_eval` state, not by following a hardcoded sequence.

## Architecture

3 agents, both orchestrators share them:

1. **ContextAgent** — parses received message, infers sender intent + emotional state + implicit asks, reasons about power dynamics for the stated relationship.
2. **ReplyAgent** — generates 2–3 variants with co-generated tone label + teaching-layer explanation + risk note (co-generation prevents explanation drift).
3. **EvalAgent** — independent quality gate: schema, tone-match, hierarchy-appropriateness, no-stereotype check. Fires regenerate on fail (max 1 retry).

See `PRD.md` §3 for why 3 agents and not 5.

## Cultural specificity boundary

The target user is ESL professionals from Indian, Chinese, and Southeast Asian backgrounds. The system does NOT bake those identities into its reasoning. Hierarchy reasoning is grounded in the relationship type the user provides per request. EvalAgent fails any output that references the user's cultural background. See `PRD.md` §5.

## Cost / billing

No API key, no per-call $ charge. Calls consume Claude Code Max plan quota via the Agent SDK. Per-call token counts log to `traces/_daily_usage.tsv` so you can sanity-check usage against Max-plan rate limits.

## v0.2 — Deferred

- Slack / Gmail / Chrome-extension integrations
- Multi-language input (currently English-only on the received message)
- Web UI
- User memory / preferences (preferred firmness, prior corrections)
- Streaming output

## Repo layout

```
reply-sensei/
├── PRD.md
├── README.md
├── pyproject.toml
├── src/
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── context_agent.py
│   │   ├── reply_agent.py
│   │   ├── eval_agent.py
│   │   └── prompts/         # version-controlled prompt markdown
│   ├── orchestration/
│   │   └── react_loop.py
│   ├── schemas/
│   │   └── response_schema.py
│   ├── cost.py
│   └── cli.py
├── evals/
│   ├── golden_set/          # 5 seeded examples
│   ├── output_evals.py
│   ├── trajectory_evals.py
│   ├── trace_evals.py
│   ├── llm_judge.py
│   └── regression_run.py
├── traces/
└── tests/
```
