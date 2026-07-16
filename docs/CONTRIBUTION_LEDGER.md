# Contribution ledger

Append-only record of the Loop Engineering V1 PR series. One entry per pull
request: the problem it solves, the outcome it delivers, its tests, the
independent review verdict, and the merge commit. Entries for a PR are
appended once its merge commit exists (i.e. in the next PR's branch; the final
PR's entry is appended to `main` directly as a docs-only follow-up).

Complete-implementation backup: branch `claude/loop-engineering-v1-j513lb`
@ `99f8734` (superseded PR #1, closed unmerged).
Job-search seed backup: commit `98e755b` (branch `backup/job-search-seed`).

---

## PR 1/12 — Repository boundary and CI scaffold (PR #2)

- **Outcome:** job-search seed retired (seed backup `backup/job-search-seed`
  @ `98e755b`); package skeleton, tooling config, CI workflow, PRD, decisions
  log, this ledger, secret-scan test.
- **Tests:** pytest 2 passed / 1 deselected; ruff clean; mypy strict clean
  (10 files); build OK; CI green on push + PR.
- **Independent review:** APPROVE (high finding — wrong preservation pointer —
  fixed before merge; nits recorded in the PR thread).
- **Merge:** squash `f0dce63`.

## PR 2/12 — Goal Contract: schema, digest locking, immutability (PR #3)

- **Outcome:** digest-locked goal contract (canonical sha256, tamper
  detection, approved amendments with recorded trail), goal-contract JSON
  Schema, domain error base, shared timestamp.
- **Tests:** pytest 12 passed / 1 deselected (digest determinism, tamper
  detection, amendment rules, roundtrip, schema self-validity); ruff clean;
  mypy strict clean (12 files); CI green.
- **Independent review:** APPROVE (no blocking findings; nits: schema not
  shipped in wheels — editable-install limitation deferred to release docs;
  format checker not enforced; digest pattern on amendment trail).
- **Merge:** squash `2612b54`.

## PR 3/12 — Durable state, ledger, checkpoints, budgets, resume (PR #4)

- **Outcome:** atomic state writes, append-only task/event ledgers, atomic-task
  record + task/run-state schemas, budgets with hard exhaustion, crash-safe
  checkpoint/resume (unverified work redone, verified never repeated,
  nothing skipped).
- **Tests:** pytest 26 passed / 1 deselected (atomic-write hygiene, roundtrips,
  checkpoint sequencing, resume semantics incl. FAILED handling, budget
  limits, ledger append-only, schema conformance); ruff clean; mypy strict
  clean (16 files); CI green.
- **Independent review:** APPROVE (findings addressed pre-merge: ledger tests
  added, FAILED-resume return semantics documented + pinned by test; noted
  lows: directory fsync gap, checkpoint seq assumptions, ledger flush-only).
- **Merge:** squash `89ef8d3`.

## PR 4/12 — Atomic planner and one-task-at-a-time execution engine (PR #5)

- **Outcome:** plan validation, deterministic execution order, goal-coverage/
  drift math; TaskQueue enforcing one-in-flight, the failed-verification gate,
  ALLOWED_TRANSITIONS, skip-with-reason, explicit plan growth.
- **Tests:** pytest 41 passed / 1 deselected (state-machine guardrails,
  planner validation/order/drift math); ruff clean; mypy strict clean
  (19 files); CI green.
- **Independent review:** APPROVE (all findings LOW: staged-for-later
  vocabulary, duplicated cycle guard, skipped-dependency interaction noted —
  handled by the engine's unsatisfiable-dependency breaker in PR 8).
- **Merge:** squash `7b13a20`.

## PR 5/12 — Verification Loops 1 and 2 (PR #6)

- **Outcome:** Loop 1 filesystem-only task verification (no executor
  narrative channel; self-verification raises), Loop 2 plan/goal-drift review
  with the hard <5% guardrail; verification-result schema + models.
- **Tests:** pytest 52 passed / 1 deselected (pass-condition semantics,
  missing artifact/evidence failures, self-verification prohibition, drift
  arithmetic, schema conformance); ruff clean; mypy strict clean (21 files);
  CI green.
- **Independent review:** APPROVE (non-blocking: UTF-8 crash surface on
  JSON pass conditions; cond.path lacks the symmetric containment guard;
  digest/file_contains/traversal test gaps; failure detail wording).
- **Merge:** squash `7505403`.

## PR 6/12 — Verification Loops 3 and 4 (PR #7)

- **Outcome:** Loop 3 independent-evidence rules (README never counts toward
  the 2/3-origin thresholds; absence claims need complete recorded search
  coverage; unsupported claims surfaced + excluded from percentages) and
  Loop 4 six-variant stability comparison preserving disagreement verbatim.
- **Tests:** pytest 66 passed / 1 deselected incl. regression tests for the
  fixed blocking finding and a claim-serialization roundtrip; ruff clean;
  mypy strict clean (23 files); CI green.
- **Independent review:** REQUEST_CHANGES — blocking HIGH finding confirmed
  (self-described origins counted toward independence thresholds → false
  "supported" possible). Fixed in `1d99851`; re-review APPROVE with
  empirical confirmation. This defect also existed in the superseded
  monolithic implementation — caught by this PR's review.
- **Merge:** squash `54886dd`.
