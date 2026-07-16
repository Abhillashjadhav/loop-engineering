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

## PR 7/12 — Recovery Controller, circuit breakers, E2E Goal Reviewer (PR #8)

- **Outcome:** all §8 breaker conditions trip with BLOCKED.md + exact unblock
  requirement (silent stops structurally impossible); recovery requeues within
  limits and records explicit repair-task plan changes; Gate A completeness
  verdicts and Gate B PD-06 thresholds — deliverable-on-interrupted impossible.
- **Tests:** pytest 87 passed / 1 deselected (every breaker, recovery paths,
  all Gate A/B verdicts and thresholds); ruff clean; mypy strict clean
  (27 files); CI green.
- **Independent review:** APPROVE (verified empirically: report-before-raise,
  boundary thresholds, weight sum; nits: DELIVERABLE_VERDICTS not consumed by
  as_verification_result, no-progress message wording, rglob counts dirs).
- **Merge:** squash `5ec689a`.

## PR 8/12 — Accuracy Evidence Pack, metrics, Learning Receipt + run engine (PR #9)

- **Outcome:** North Star credited only for verified goals; PD-03 leading
  metrics; full evidence pack + Learning Receipt; the deterministic run engine
  assembling PRs 2–7 with bounded auto-repair and crash-safe resume.
- **Tests:** pytest 92 passed / 1 deselected (auto-repair-below-70 delivery,
  planted failure recovery, persistent-failure safe stop, North-Star crediting
  across all verdicts, pack content checks); ruff clean; mypy strict clean
  (30 files); CI green. engine.py byte-identical to the verified complete
  implementation.
- **Independent review:** APPROVE (verified: pack on non-deliverable verdict
  impossible; claims cannot double-persist on resume; interrupt leaves
  resumable state; nits: deliverable-set expressed in three places, redundant
  loop2 records inflate a cosmetic count, dead `deliverable()` helper).
- **Merge:** squash `1d9597a`.

## PR 9/12 — Claude Code skill and role agents (PR #10)

- **Outcome:** /loop-engineer orchestration skill (six modes; Claude
  orchestrates, Python validates; BLOCKED.md surfaced verbatim), eight role
  agents with enforced separation, per-agent eval fixtures with planted
  failures, permission policy enforced by tests.
- **Tests:** pytest 98 passed / 1 deselected (fixture structure, fire/no-fire
  cases, permission policy, executor self-verification prohibition, planted
  failures); ruff clean; mypy strict clean (30 files); CI green. Zero Python
  source changes.
- **Independent review:** APPROVE (tense nit on evals/README fixed pre-merge;
  noted: may_write substring guard granularity, read_only/may_write pairing
  reconciled by agent definitions).
- **Merge:** squash `aa9cfca`.

## PR 10/12 — GitHub identity and complete repository inventory (PR #11)

- **Outcome:** identity confirmation only from >=2 corroborating public
  attributes (collisions block; URL alone proves nothing); full-pagination
  inventory with forks excluded from authored scoring, stars as distribution
  signals only, inaccessible content recorded honestly; fixture/live
  data-source protocol; planted synthetic corpus.
- **Tests:** pytest 106 passed / 1 deselected; ruff clean; mypy strict clean
  (33 files); CI green.
- **Independent review:** APPROVE (medium finding fixed pre-merge: empty
  placeholder expected-attributes could false-match — now non-matching with a
  regression test; nits: lexical page sort, silent missing-candidates file,
  test filename breadth).
- **Merge:** squash `e1ccaad`.

## PR 11/12 — AI-slop rubric, scoring and portfolio aggregation (PR #12)

- **Outcome:** ten-dimension deterministic rubric; AI-assistance and slop risk
  as separate axes; triple-gated negative classification (slop >= 70 AND
  confidence >= 70 AND recorded counter-evidence); exact AI-authorship
  percentages rejected (bands only); dual-weighted person aggregation with an
  explicit cannot-conclude list.
- **Tests:** pytest 113 passed / 1 deselected (popularity-is-not-quality,
  AI-assistance-is-not-slop, triple gate, banding, percentage rejection,
  dual-weighted aggregation over planted fixtures); ruff clean; mypy strict
  clean (36 files); CI green. errors.py byte-identical to the verified
  complete implementation.
- **Independent review:** APPROVE (verified: no fairness-gate bypass; stars
  never feed technical scores; count-weighted 40% vs active-weighted 4.2%
  shallow share shows high-star dumps cannot dominate; clock pinned in the
  aggregation test per finding; regex phrasing gaps recorded as
  defense-in-depth nits).
- **Merge:** squash `65967e5`.

## PR 12/12 — Synthetic demonstration, live-audit blocker report, release docs (PR #13)

- **Outcome:** audit runner (per-subject task graphs, evidence-backed claims,
  six analysis variants, repair hooks), the loop-engineering CLI, example
  contracts/subjects, the live-audit blocking report (exact missing evidence,
  three unblock paths, zero invented conclusions), release documentation,
  unconditional CI smoke of the full synthetic demonstration.
- **Tests:** pytest 123 passed / 1 deselected (full synthetic E2E with per-
  stage Loop 2 and preserved six-run disagreement; interrupted-run resume
  without skipping; identity-ambiguity blocking; full CLI smoke); ruff clean;
  mypy strict clean (38 files); build OK; CLI demo Gate A COMPLETE,
  Gate B 100/100 GOAL_MATCH; CI green.
- **Independent review:** APPROVE — reviewer independently reproduced the
  demo, interrupt→resume, read-only `verify`, the loud `--live` failure, the
  honesty greps (no finding attached to either named subject anywhere), and
  the convergence claim (src/ differs from the verified backup only by the
  four review-driven improvements).
- **Merge:** squash `978a9a4`.

---

Series complete: 12/12 merged. The only src/ divergences from the superseded
monolithic implementation are review-driven improvements (Loop-3 README-
threshold false-supported fix; identity empty-placeholder hardening; two
docstring clarifications), each with regression tests — evidence that the
atomic-PR review process caught real defects the monolith carried.
