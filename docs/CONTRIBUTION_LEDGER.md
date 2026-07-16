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
