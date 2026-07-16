# Evals

## `agents/`

One `cases.yaml` per Claude role agent (mirroring `.claude/agents/`). Each
fixture declares the agent's input contract, output schema, read/write
permissions, prohibitions, fire/no-fire cases, a planted failure with its
expected detection, goal-drift handling, uncertainty handling, and the
self-verification rule. `tests/test_agent_evals.py` validates the structure
and enforces the permission policy (reviewers read-only; the executor may
write only artifacts/evidence and may never verify its own work).

## `fixtures/github/`

Synthetic public-GitHub snapshots in the `FixtureDataSource` layout:

```
profiles/<login>.json          # candidate profile per login
candidates/<subject-slug>.json # candidate login list per subject
repos/<login>/page-N.json      # paged repository listings
```

Planted cases the test suite will depend on (the fixtures land with the github-authority-audit use case in the next PRs):

- `synthetic-builder` — high-quality subject: substantive repos with tests/CI,
  an educational notes repo, a fork (`upstream-sdk`, must be excluded from
  authored scoring), an archived repo, and a second page (pagination).
- `synthetic-templater` — slop-heavy subject: two one-shot template dumps with
  unbacked README claims (classified LIKELY_SHALLOW_OR_TEMPLATED with recorded
  counter-evidence), a borderline repo (`prompt-pack-07`) that flips only
  under the skeptical six-run variant, a genuinely valuable curated list
  (high distribution ≠ slop), an empty repo, a low-confidence repo
  (INSUFFICIENT_EVIDENCE), and an inaccessible repo (recorded honestly).
- `ambiguous-a` / `ambiguous-b` — identity collision: both match the same
  expected attributes, so analysis must block.
- `weak-match` — only one attribute matches: identity must not confirm.

Live web/GitHub tests are optional (`pytest -m live`) and never required for
offline CI.
