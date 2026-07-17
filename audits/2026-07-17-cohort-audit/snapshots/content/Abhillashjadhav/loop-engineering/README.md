# Loop Engineering

A self-verifying autonomous goal loop. You hand it **one** locked goal —
statement, expected output, North Star Metric, scope, permissions,
verification rules, budget — and it plans atomic tasks, executes them one at a
time, independently verifies every step, checks itself for goal drift,
triangulates every material claim, stress-tests its own conclusion six ways,
repairs its own gaps, and ships the result with an **Accuracy Evidence Pack**
that explains why the output can be trusted — or stops loudly with the exact
reason it can't.

The North Star is `human_active_minutes_saved_per_successfully_verified_goal`.
Raw speed without verified completion is not success.

## How it works

```
goal.yaml ──init──▶ digest-locked contract (immutable during a run)
                      │
                      ▼
              planner: atomic tasks (each with a pass condition
              defined BEFORE execution)
                      │
        ┌─────────────▼──────────────┐
        │  one task at a time        │◀── recovery controller
        │  execute ─▶ Loop 1 verify  │    (requeue / repair tasks /
        │  (executor never verifies  │     circuit breakers with
        │   its own work)            │     blocking reports)
        └─────────────┬──────────────┘
                      ▼
   Loop 2: plan/goal-drift check (< 5% or halt)
   Loop 3: independent evidence verification per material claim
           (2 origins normal, 3 high-impact, README ≠ corroboration,
            absence claims need search coverage)
   Loop 4: six-run stability (standard, fresh plan, reordered sources,
           skeptical, conclusion-blind, replication) — disagreement is
           preserved, never averaged
                      ▼
   End-to-End Goal Reviewer (fresh context, read-only)
     Gate A: process completeness   Gate B: goal-match 0–100
     80+ GOAL_MATCH · 70–79 deliver with caveats · <70 auto-repair
     interrupted/incomplete runs can NEVER be delivered as success
                      ▼
   outputs/<goal-id>/ — Accuracy Evidence Pack + Learning Receipt
```

Every state write is atomic (`os.replace`); a killed run resumes from the
first task that is not both executed **and** verified, repeating no verified
work and skipping nothing. Circuit breakers stop the loop on repeated
actions without new evidence, repeated failures, stalled progress, attempt
limits, budget exhaustion, forbidden actions, inaccessible sources, or
unresolved identity — always with a `BLOCKED.md` naming the exact unblock
requirement. It never terminates silently.

## Quickstart

```bash
pip install -e ".[dev]"

# full synthetic demo (offline, deterministic)
loop-engineering audit-github \
  --subjects examples/subjects.synthetic.yaml \
  --fixtures evals/fixtures/github

# inspect the result
cat outputs/github-authority-audit-synthetic/accuracy-evidence.md

# the general flow for any goal
loop-engineering init examples/goal.synthetic.yaml
loop-engineering plan github-authority-audit-synthetic --fixtures evals/fixtures/github
loop-engineering run  github-authority-audit-synthetic --fixtures evals/fixtures/github
loop-engineering status <run-id>
loop-engineering verify <run-id>      # read-only Gate A recheck
loop-engineering report <run-id>
loop-engineering resume <run-id>      # after any interruption
```

In Claude Code, `/loop-engineer` is the single entry point (modes: start,
status, resume, report, verify-only, use-case <name>); it orchestrates while
the Python CLI validates state and policy.

## First use case: public GitHub authority audit

`use_cases/github-authority-audit/` audits whether a public GitHub portfolio
demonstrates substantive GenAI proficiency, human reasoning, education/curation
value, distribution strength, AI-assisted-but-useful creation, or
shallow/templated work — from public artifacts only, with hard fairness rules:

- identity requires ≥ 2 corroborating public attributes (a URL proves nothing);
- forks are excluded from authored-code scoring; popularity is a reach signal,
  never quality; AI assistance is **not** slop;
- a shallow/templated label requires slop risk ≥ 70 **and** confidence ≥ 70
  **and** a recorded counter-evidence review;
- exact AI-authorship percentages are rejected outright — only conservative
  ranges with confidence (`estimated_ai_assisted_code_share_range`);
- what cannot be concluded is stated explicitly.

The two initial live subjects are configured in `examples/subjects.yaml`. The
live path requires an environment permitted to fetch public GitHub data (or
pre-fetched snapshots); it fails loudly rather than inventing results.

## Repository map

| Path | What it is |
|---|---|
| `schemas/` | JSON Schemas: goal contract, task, verification, run state |
| `src/loop_engineering/contracts/` | digest-locked immutable goal contract |
| `src/loop_engineering/planning/` | plan validation, coverage, goal-drift math |
| `src/loop_engineering/runtime/` | engine, state, ledgers, queue, budget, checkpoints, duplicate detection, circuit breakers |
| `src/loop_engineering/verification/` | Loops 1–4 + end-to-end reviewer |
| `src/loop_engineering/recovery/` | failure routing, repair tasks |
| `src/loop_engineering/reporting/` | metrics, Accuracy Evidence Pack, Learning Receipt |
| `src/loop_engineering/use_cases/` | use-case modules (github_authority_audit) |
| `use_cases/github-authority-audit/` | use-case config, rubric, docs |
| `.claude/` | `/loop-engineer` skill + 8 role agents |
| `evals/` | agent eval fixtures + synthetic GitHub fixtures |
| `examples/` | goal contracts and subject files |
| `tests/` | 100+ deterministic tests incl. E2E, resume, and repair demos |

## Checks

```bash
python -m pytest        # all tests (live tests excluded by default)
ruff check src tests && ruff format --check src tests
python -m mypy          # strict
python -m build
```

Adding a use case = adding a module under `src/loop_engineering/use_cases/`
plus config under `use_cases/<name>/`. The runtime is never rewritten.

## V1 limitations

- Live web/GitHub retrieval is delegated to the Claude Code skill layer
  (snapshots into a fixture directory); the Python runtime is deliberately
  offline and deterministic.
- The live audit of the two named subjects has not been executed in this
  environment (GitHub access here is repo-scoped); the system ships with the
  synthetic demonstration and the live goal contract ready to run. The exact
  missing evidence and unblock paths are recorded in
  [docs/live-audit-blocked.md](docs/live-audit-blocked.md).
- Six-run stability variants share the deterministic scoring core; stance and
  ordering vary per variant. With LLM executors the variance will be larger —
  the comparison machinery is built for that.
