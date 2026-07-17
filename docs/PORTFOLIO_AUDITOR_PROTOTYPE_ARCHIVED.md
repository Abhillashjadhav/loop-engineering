# GitHub Portfolio Auditor — archived loop-engineering prototype

> **Status: ARCHIVED PROTOTYPE — reference only. Not part of loop-engineering
> `main`. Do not build a runtime dependency on this branch.**

## What this is

An early prototype of the **GitHub Portfolio Auditor** (Milestones M1–M2) that
was developed inside `Abhillashjadhav/loop-engineering` on an isolated
integration branch. It was **never merged to `main`** and was **created in the
wrong repository**.

## Final product decision (supersedes this prototype)

- **GitHub Portfolio Auditor** now belongs in
  **`Abhillashjadhav/production-engineering-os`** — final development happens
  there, not here.
- **Personal Chief of Staff** belongs in `Abhillashjadhav/loop-engineering`
  (see PR #14).
- The existing **cohort / GitHub authority audit** remains in
  `loop-engineering` (unaffected by this archive).

This branch exists only to preserve the completed M1/M2 work for reference when
rebuilding the auditor in `production-engineering-os`. **No code in
loop-engineering `main` or any other branch should import from or depend on
this archive branch.** It will not be maintained.

## Preserved capabilities

### M1 — product contract & architecture (reusable as-is)
- `src/loop_engineering/use_cases/portfolio_auditor/contract.py` — immutable,
  **digest-locked `ProductDecisionContract`** reusing the Loop Engineering
  candidate-freezing primitives; schema validation; `amend(approver+reason →
  new version)`; typed policy accessors.
- `use_cases/portfolio-auditor/contract.yaml` — the shipped **locked contract**:
  locked product decisions PD-PA-01..07, AI-slop 3-verdict policy (hard verdict
  gated at confidence ≥ 70 + counter-evidence review; forbidden sole bases),
  5-grade business-accuracy scale (PROVEN/LIKELY/NOT_PROVEN/CONTRADICTED/
  INSUFFICIENT_EVIDENCE), 5 recommendation verdicts
  (FIX/SHOWCASE/CONSOLIDATE/REBUILD/KEEP_AS_IS), prioritization formula, 9
  auto-merge gates + 8 forbidden auto-merge actions, safety/privacy rules,
  metrics, and the integration boundary.
- `src/loop_engineering/use_cases/portfolio_auditor/models.py` — `Finding`
  (7 required fields) + evidence/verdict/severity vocabulary, confidence
  clamping, prioritization scoring, and the *"a numeric score never overrides a
  material high-confidence finding"* guard.
- `schemas/portfolio-auditor-contract.schema.json`.
- `docs/portfolio-auditor/` — ADR, audit lifecycle, evidence & scoring model,
  AI-slop policy, remediation/auto-merge policy, threat model, test strategy,
  acceptance criteria.

### M2 — broad, read-only repository scanner (reusable as-is)
- `src/loop_engineering/use_cases/portfolio_auditor/datasource.py` —
  `RepositorySource` protocol + `FixtureRepositorySource` + loud
  `LiveRepositorySource` (no network, no model calls).
- `src/loop_engineering/use_cases/portfolio_auditor/scanner.py` — deterministic,
  mechanical signal extraction: metadata, language/stack, README/docs, tests/CI,
  security & dependency signals (lockfiles, manifests, declared-dep count,
  name/version-aware pinned-deps heuristic, **redacted** secret scanning —
  `rule/path/line` only, never the value), freshness (`days_since_pushed` from
  an injected `now`), packaging, and mechanical claim extraction.
- Fixture portfolio `evals/fixtures/portfolio_auditor/demo-portfolio/` —
  `healthy-lib`, `slop-wrapper` (planted claims + placeholder secrets),
  `stale-fork`, `internal-service` (PRIVATE, planted placeholder key).

### M2 Stage-1 confidence run
- `tests/test_portfolio_auditor_m2_confidence.py` — 12 checks: complete
  inventory, correct visibility/fork, language/stack, README/docs/test/CI
  signals, security/dependency signals, secret detected-but-fully-redacted, no
  private-source leakage, healthy signals not treated as risk, slop-wrapper
  risk signals **without** any premature AI-slop verdict, **byte-identical
  repeated runs**, fixture-backed evidence, and no real GitHub access. (Added
  after M2 merge as part of the Stage-1 confidence audit; green, but not
  separately independently reviewed.)

## Tests & review state at archival

- M1: 25 tests · independent fresh-context review **APPROVE**, 0 blocking.
- M2: 17 scanner tests + 12 Stage-1 confidence tests · independent review
  raised 1 blocking finding (pinned-deps false-negative on `x`-named packages),
  which was fixed with a regression test → **re-review APPROVE**, 0 blocking.
- Full suite at the M2 merge commit (`c6f0a7d`): **178 passed**, `ruff` +
  `ruff format --check` + `mypy --strict` + `python -m build` green, and the
  repo-wide real-secret scan green.
- Milestones M3–M9 and the final feature→main draft PR were **not started**.

## Reusable product decisions, rubrics & fixtures (portable to production-engineering-os)

- The locked `ProductDecisionContract` and its policies (AI-slop, business
  accuracy, recommendation verdicts, prioritization, remediation/auto-merge).
- The evidence & scoring model (evidence-independence via `origin`,
  corroboration thresholds, confidence gating, INSUFFICIENT_EVIDENCE floors).
- The broad-scan signal taxonomy and the deterministic scanner.
- The synthetic fixture portfolio (healthy / shallow-wrapper / stale-fork /
  private-with-secret) and the planted-failure conventions.
- The design docs under `docs/portfolio-auditor/`.

## Provenance

- Archived from integration branch `feature/github-portfolio-auditor-v1` at
  commit `c6f0a7d` (Merge M2 — Broad repository scanner, PR #16).
- Never merged to `main`; `main` remained at `1070ce0` throughout.
- Superseded prototype branches (`feature/github-portfolio-auditor-v1`,
  `feat/pa-m1-contract`, `feat/pa-m2-scanner`) were deleted after this archive
  captured all M1/M2 work.
