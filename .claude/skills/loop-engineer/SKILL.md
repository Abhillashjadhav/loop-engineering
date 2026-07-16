---
name: loop-engineer
description: >
  Single entry point for Loop Engineering: run one locked goal autonomously
  through atomic tasks, four verification loops, an independent end-to-end
  review, and an Accuracy Evidence Pack. Use for: "start a loop-engineering
  goal", "resume run", "status of run", "verify run", "report run",
  "audit github subjects", or any /loop-engineer invocation. Supports modes:
  start, status, resume, report, verify-only, use-case <name>.
---

# /loop-engineer — orchestration skill

You are the orchestrator. **Claude orchestrates; deterministic Python
validates.** Never hand-maintain state the CLI owns (task statuses, digests,
budgets, verification verdicts) — always go through `loop-engineering`
commands, which enforce the contracts, state machine, breakers, and evidence
rules.

## Modes

Parse the user's request into one of:

- `start <goal.yaml>` — lock and run a new goal:
  1. `loop-engineering init <goal.yaml>` (locks the contract, prints digest).
  2. `loop-engineering plan <goal-id> [--subjects ... --fixtures ...]` and show
     the concise plan to the user for one-time approval (PD-01).
  3. On approval: `loop-engineering run <goal-id> ...` and let it continue
     autonomously. Do not re-prompt the user between tasks.
- `status <run-id|run-dir>` — `loop-engineering status <run>`.
- `resume <run-id|run-dir>` — `loop-engineering resume <run>` (safe after any
  interruption; verified work is never repeated, unverified work is redone).
- `report <run-id|run-dir>` — `loop-engineering report <run>`; deliver the
  Accuracy Evidence Pack summary and the Learning Receipt.
- `verify-only <run-id|run-dir>` — `loop-engineering verify <run>` (read-only
  Gate A recheck; never mutates state).
- `use-case github-authority-audit` — one-shot audit:
  `loop-engineering audit-github --subjects <file> [--fixtures <dir> | --live]`.

## Live data for the GitHub audit

Python never fetches the live web. When a live audit is requested and direct
GitHub access is unavailable, you (the skill layer) fetch public snapshots
with your own tools (WebFetch / GitHub tooling), write them into a fixture
directory in the FixtureDataSource layout
(`profiles/<login>.json`, `candidates/<slug>.json`, `repos/<login>/page-N.json`),
record retrieval timestamps, then run with `--fixtures <dir>`. If you cannot
fetch, report the exact blocking reason — never invent results (Hard rule:
honesty over helpfulness).

## Hard rules (mirror of PD-04 — the CLI enforces them; you must not work around them)

- Never continue past a failed task verification by hand.
- Never edit run state, ledgers, digests, or verification files directly.
- Never present an exact AI-authorship percentage; ranges only.
- Never deliver a run whose Gate B verdict is not GOAL_MATCH or
  GOAL_MATCH_WITH_CAVEATS.
- If the CLI exits non-zero with a blocking report, surface
  `reports/BLOCKED.md` verbatim, including the exact unblock requirement.

## Subagents

For fresh-context reviews, delegate to the role agents in `.claude/agents/`
(planner, executor, task-verifier, goal-drift-reviewer, evidence-verifier,
stability-reviewer, end-to-end-goal-reviewer, recovery-controller). The
executor must never verify its own work; reviewers are read-only.
