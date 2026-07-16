# Use case: Public GitHub Authority Audit

Determines, from public evidence only, whether a subject's public GitHub
portfolio demonstrates substantive GenAI technical proficiency, meaningful
human/product/engineering reasoning, education/curation strength, distribution
strength, heavily AI-assisted but useful creation, or shallow/templated
"AI slop" — without inferring private intent or exact authorship.

## Boundaries (PD-08, spec §11)

- Assesses **public artifacts and public claims**, never personality or private intent.
- "AI slop" is an operational repository-quality label, not a moral judgment.
- Exact AI-authorship percentages are never stated — only conservative ranges
  (`0-25`, `25-50`, `50-75`, `75-100`, `INSUFFICIENT_EVIDENCE`) with confidence.
- Every negative classification carries the strongest counter-evidence found.
- Identity must be corroborated by at least two public attributes before any
  repository is analysed; ambiguity blocks the run.

## Running

Synthetic (offline, deterministic — this is what CI exercises):

```bash
loop-engineering audit-github \
  --subjects examples/subjects.synthetic.yaml \
  --fixtures evals/fixtures/github
```

Live subjects (requires an environment allowed to fetch public GitHub data):

```bash
loop-engineering audit-github --subjects examples/subjects.yaml --live
```

The `--live` path fails loudly with the exact unblock requirement when the
environment cannot reach GitHub: fetch public snapshots via the
`/loop-engineer` skill layer into a fixture directory, then re-run with
`--fixtures <dir>`. Results are never invented for missing live evidence.

## Files

- `config.yaml` — thresholds, evidence rules, fairness rules.
- `rubric.yaml` — the 10 dimensions and derived-score formulas (documentation of
  the deterministic implementation in
  `src/loop_engineering/use_cases/github_authority_audit/rubric.py`).
- `../../examples/subjects.yaml` — the two initial live subjects.
- `../../examples/subjects.synthetic.yaml` — the synthetic subjects used by CI.
