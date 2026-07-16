# Loop Engineering — project instructions

Self-verifying autonomous goal loop. One locked goal in; verified output plus
an Accuracy Evidence Pack out. PRD: `prds/2026-07-16-loop-engineering-v1.md`.
Architecture log: `DECISIONS.md` (append one line per meaningful choice).

## Ground rules (locked product decisions — do not reinterpret)

1. **Honesty over helpfulness.** Never fabricate results, evidence, scores, or
   completion; "no result" always beats an invented one.
2. **Claude orchestrates; Python validates.** No model SDK/API calls in the
   Python runtime. No services, queues, databases, vector stores, or web UI;
   file-backed JSON/JSONL/YAML state only.
3. Keep `python -m pytest`, `ruff check`, `ruff format --check`,
   `python -m mypy` (strict), and `python -m build` green — no exceptions.
4. Never require the network in default tests; live tests carry
   `@pytest.mark.live`.

The full instruction set (verification loops, evidence rules, use-case
editing rules) lands with the corresponding PRs in the series tracked by
`docs/CONTRIBUTION_LEDGER.md`.
