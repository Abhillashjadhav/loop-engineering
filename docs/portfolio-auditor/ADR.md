# ADR — GitHub Portfolio Auditor V1 architecture

**Status:** Accepted (Milestone 1) · **Base:** `main` @ `1070ce0` · **Branch:** `feature/github-portfolio-auditor-v1`

## Context

The Portfolio Auditor inspects accessible public and private GitHub
repositories and recommends, per repository, whether to **FIX / SHOWCASE /
CONSOLIDATE / REBUILD / KEEP_AS_IS** — evidence-backed, confidence-gated, and
with a repository-level AI-slop verdict. It ships as an **isolated capability
inside `Abhillashjadhav/loop-engineering`** ("Production Engineering OS"), while
other V3 work runs in parallel branches/PRs.

## Decisions

1. **New use-case module, not a new repo or a rewritten runtime.** All code
   lives under `src/loop_engineering/use_cases/portfolio_auditor/`, config under
   `use_cases/portfolio-auditor/`, fixtures under
   `evals/fixtures/portfolio_auditor/`. This obeys the locked project rule
   ("new use cases are modules … never a new repo or a rewritten runtime").

2. **Reuse the Loop Engineering spine; never duplicate it.**

   | Need | Reused mechanism |
   |---|---|
   | Candidate/contract freezing | `contracts.goal_contract` (`canonical_json`, `compute_digest`, `verify_integrity`) |
   | Evidence ledger independence | `domain.models.EvidenceItem.origin`, `Claim`, `SearchCoverage` |
   | Data-source protocol | `use_cases.github_authority_audit.datasource` pattern (fixture + loud live placeholder) |
   | Review isolation / merge gating | `verification.e2e_reviewer` (Gate A/B), `.claude/agents/*` |
   | Deterministic reporting | `reporting.evidence_pack`, `reporting.metrics` |
   | Run state / circuit breakers | `runtime.{state,ledger,checkpoint,circuit_breaker}` |

3. **Claude orchestrates; Python validates.** No model SDK/API calls in the
   Python runtime. Inspectors (fixtures in CI, agents live) record *observable
   signals*; Python scores them **deterministically**. The same commit + rubric
   + config yields materially consistent results.

4. **File-backed state only.** JSON/JSONL/YAML. No services, queues, databases,
   vector stores, or web UI. The dashboard is dashboard-*ready data* + a
   self-contained renderable, not a hosted service.

5. **Two-stage operating model.** Broad scan of all repos → risk + strategic
   selection → deep inspection of high-risk/marketable repos → recommend →
   prioritized remediation backlog → sandbox remediation PRs → independent
   review + CI → gated auto-merge → post-remediation re-audit.

6. **Stable interfaces for parallel-work isolation.** The auditor exposes
   `RepositorySource` (protocol), `Rubric` (protocol), and report dataclasses.
   It **imports from** the shared spine but **adds no imports into** existing
   modules and edits no existing files except additive registration — so
   parallel V3 changes cannot conflict with it and vice-versa.

7. **A digest-locked `ProductDecisionContract` governs the run.** It pins the
   verdict vocabularies, the AI-slop policy, the business-accuracy scale, the
   prioritization formula, the remediation/auto-merge policy, metrics, safety
   rules, and the integration boundary. It is immutable during a run; changes
   require `amend()` with an approver + reason (new version).

## Planned module layout (filled in milestone by milestone)

```
src/loop_engineering/use_cases/portfolio_auditor/
  contract.py       # M1 — digest-locked ProductDecisionContract + accessors
  models.py         # M1 — evidence/verdict/severity model + scoring helpers
  datasource.py     # M2 — RepositorySource protocol + FixtureRepositorySource
  scanner.py        # M2 — broad, read-only mechanical scan
  selection.py      # M3 — strategic config + risk score + deep-inspect selection
  inspect.py        # M4 — deep evidence-backed dimension rubrics
  classify.py       # M5 — AI-slop verdict (evidence + confidence gated)
  report.py         # M6 — portfolio JSON/Markdown/scorecards/backlog/evidence index
  remediation.py    # M7 — plan + PR orchestration (dry-run) + auto-merge gates
  reaudit.py        # M8 — post-remediation re-scan + closure classification
  runner.py         # end-to-end wiring for a fixture-backed audit
```

## Consequences

- The auditor is testable fully offline; CI never needs the network.
- Reuse keeps the digest-lock, evidence-independence, and gating semantics
  identical across the codebase (one source of truth per concern).
- The cost is discipline: every judgment must arrive as a recorded signal +
  evidence, never as a Python-side inference, and every material finding must
  carry evidence and confidence.
