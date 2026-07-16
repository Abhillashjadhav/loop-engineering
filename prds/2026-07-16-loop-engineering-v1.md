# PRD: Loop Engineering V1 — self-verifying autonomous goal loop

**Date:** 2026-07-16
**Status:** Approved

Derived directly from the "Loop Engineering V1 — Authoritative Build Specification"
(task brief, 2026-07-16). The specification carries locked product decisions
PD-01..PD-08 marked "approved — do not reinterpret"; this PRD records them in the
repo's standard 5-field format. The full specification is the authority; on any
conflict the specification wins.

## Problem

Multi-step goals given to an AI agent today require repeated human prompting
("continue", "now do X", "did you check Y?") and produce unverified output the
human must re-check by hand. The human pays twice: once to babysit the loop,
once to audit the result.

## User

Abhillash (goal owner), and any future operator of the reusable spine. Current
alternative: manually driving Claude Code turn by turn and manually verifying
every claim in the output.

## Success metric

North Star: `human_active_minutes_saved_per_successfully_verified_goal` —
baseline manual minutes minus actual human active minutes, credited **only**
when the goal is successfully verified (E2E goal-match ≥ 70 with process
completeness). Raw speed without verified completion is not success.

## Scope (v1)

- Digest-locked, immutable Goal Contract; one approval, then autonomous.
- Atomic task engine: one task at a time, independent verification, checkpoints,
  crash-safe resume, budgets, duplicate detection, circuit breakers.
- Four nested verification loops (task, plan/goal-drift, independent evidence,
  six-run final stability) + independent End-to-End Goal Reviewer (Gate A/B).
- Automatic repair below goal-match 70; delivery with caveats at 70–79.
- Accuracy Evidence Pack + Learning Receipt on every successful run.
- First use case: public GitHub authority audit (Aakash Gupta, Shubham Saboo)
  with synthetic-fixture support for offline CI.

## Out of scope (cut from v1)

- Services, queues, databases, vector stores, web UI, agent frameworks,
  cloud infrastructure (file-backed JSON/JSONL/YAML state only).
- Anthropic/OpenAI/other model SDK or API calls (Claude Code skills/subagents
  + deterministic local Python only).
- Private-intent or exact-authorship claims about audited persons.
- Live web/GitHub access as a CI requirement (live tests optional only).

## Non-goals (failure modes)

- A "successful" verdict on an interrupted, incomplete, or unverified run.
- Any material unsupported claim in final output; goal drift ≥ 5%; silent scope
  expansion; executor self-verification; indefinite retry; hidden uncertainty.
- Claiming exact AI authorship percentages without provenance evidence.
- Silent termination — every stop must produce a blocking report with the exact
  unblock requirement.

## Decisions log

See /DECISIONS.md (running architectural log).
