# Test strategy

## Principles

- **TDD, red first.** Failing tests are committed separately before
  implementation in every milestone.
- **Deterministic and offline.** Default tests never touch the network; live
  paths carry `@pytest.mark.live` and are excluded from CI.
- **Signals in, scores out.** Tests feed recorded inspector signals (fixtures)
  and assert deterministic scores/verdicts — never model output.

## Per-milestone gate (all must be green to merge into the integration branch)

1. `python -m pytest` (full suite)
2. `ruff check src tests` + `ruff format --check src tests`
3. `python -m mypy` (strict)
4. `python -m build` (packaging) at least at milestone boundaries
5. **Independent fresh-context read-only review** (a subagent that did not write
   the code) → reconcile → fix confirmed blocking findings → rerun gates.

## Test classes

- **Contract/policy tests** — digest lock, tamper detection, amend rules, locked
  policy content (M1).
- **Scanner tests** — mechanical signal extraction over fixture repos (M2).
- **Selection tests** — deterministic risk/priority ranking, flagship inclusion,
  config validation (M3).
- **Rubric tests** — planted signals → expected dimension scores + evidence
  requirements; INSUFFICIENT_EVIDENCE floors (M4).
- **Classifier tests** — planted `AI_SLOP` / `NOT_AI_SLOP` cases,
  **false-positive** cases (must not hard-label), contradiction handling, and
  **repeated-run consistency** (M5).
- **Report tests** — deterministic JSON/Markdown/scorecard/backlog output (M6).
- **Remediation tests** — gate evaluation truth tables, dry-run PR orchestration,
  refusal of forbidden auto-merge actions (M7).
- **Re-audit tests** — closure classification (fixed/partially/not/regressed),
  regression detection, evidence retention (M8).
- **Dogfood / planted-failure tests** — each planted defect (unsupported claim,
  duplicated architecture, broken setup, missing tests, eval drift, shallow
  generated content, unsafe dependency, misleading production-readiness) is
  detected by the relevant gate (M9).

## Guardrail properties asserted

Repeated-run consistency · false-positive rate on planted-clean repos · no
unsupported hard verdicts · no private-data leakage in public output · no
destructive changes · no incorrect auto-merge · evidence retention across
re-audits.
