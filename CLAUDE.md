# Loop Engineering — project instructions

Self-verifying autonomous goal loop. One locked goal in; verified output plus
an Accuracy Evidence Pack out. Full spec context: `prds/2026-07-16-loop-engineering-v1.md`
(PRD) and `DECISIONS.md` (architecture log — append one line per meaningful choice).

## Ground rules (locked product decisions — do not reinterpret)

1. **Honesty over helpfulness.** Never fabricate results, evidence, scores, or
   completion. A blocked run writes `BLOCKED.md` with the exact unblock
   requirement; "no result" is always preferable to an invented one.
2. **The contract is immutable during a run.** Changes require `amend()` with
   an approver + reason (new version), never in-place edits.
3. **Only VERIFIED counts.** No next task after a failed verification; the
   executor never verifies its own work; interrupted/incomplete runs are never
   delivered as success.
4. **Evidence rules:** material claims need ≥2 independent origins (≥3
   high-impact); a README is not corroboration; absence claims need recorded
   search coverage; unsupported claims are excluded from percentages, loudly.
5. **PD-08 fairness:** public artifacts only; no private-intent claims; never
   exact AI-authorship percentages (ranges + confidence only); negative
   classifications need slop ≥ 70, confidence ≥ 70, and counter-evidence.
6. **Claude orchestrates; Python validates.** No model SDK/API calls in the
   Python runtime. New use cases are modules under
   `src/loop_engineering/use_cases/` + config under `use_cases/<name>/` —
   never a new repo or a rewritten runtime. No services, queues, databases,
   vector stores, or web UI; file-backed JSON/JSONL/YAML state only.

## Commands

```bash
pip install -e ".[dev]"                      # setup
python -m pytest                             # tests (live tests excluded by default)
python -m pytest -m live                     # optional live tests only
ruff check src tests && ruff format --check src tests
python -m mypy                               # strict, must stay clean
python -m build                              # packaging check
loop-engineering audit-github --subjects examples/subjects.synthetic.yaml \
  --fixtures evals/fixtures/github           # full offline E2E demo
```

Entry point for orchestration: the `/loop-engineer` skill
(`.claude/skills/loop-engineer/SKILL.md`); role agents live in `.claude/agents/`.

## Architecture map

- `contracts/goal_contract.py` — canonical digest (`sha256` over sorted-key
  JSON minus the digest field), lock/verify/amend.
- `runtime/engine.py` — the run loop: plan → (one task → Loop 1 verify) →
  Loop 2 drift → Loop 3 evidence → Loop 4 six-variant stability → E2E review
  (Gate A/B) → auto-repair (<70) → evidence pack. `Engine.resume()` restores
  from the latest checkpoint; EXECUTED-but-unverified work is redone, VERIFIED
  work is never repeated.
- `runtime/task_queue.py` — the task state machine
  (`ALLOWED_TRANSITIONS` in `domain/models.py` is the single source of truth).
- `runtime/circuit_breaker.py` — every hard stop writes `reports/BLOCKED.md`.
- `verification/` — loops 1–4 + `e2e_reviewer.py` (PD-06 thresholds live here).
- `use_cases/github_authority_audit/` — rubric formulas are deterministic;
  inspectors (fixtures or agents) record *observable signals*, Python scores
  them. Update `use_cases/github-authority-audit/rubric.yaml` if formulas move.

## Editing rules

- Tests before or with implementation; keep `python -m pytest`, `ruff`,
  `mypy --strict`, and `python -m build` green — no exceptions.
- Never require the network in default tests; live tests carry `@pytest.mark.live`.
- The synthetic fixtures in `evals/fixtures/github/` encode planted cases
  (slop, borderline-flip, identity collision, low confidence). If you change
  rubric formulas, re-derive the planted expectations rather than loosening
  the assertions.
- `runs/`, `outputs/`, `contracts/` are generated at runtime and gitignored.
