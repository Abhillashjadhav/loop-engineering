# Loop Engineering

A self-verifying autonomous goal loop: one locked goal in; verified output
plus an Accuracy Evidence Pack out.

This repository is being assembled as a sequence of focused, independently
reviewable pull requests. The capabilities land in order: goal contract →
durable state → task engine → four verification loops → recovery + end-to-end
review → evidence pack → Claude Code skill/agents → GitHub authority audit
use case → synthetic demonstration and release documentation.

Full product documentation lands with the final release PR. Until then:

- `prds/2026-07-16-loop-engineering-v1.md` — the approved PRD
- `DECISIONS.md` — the running architecture log
- `docs/CONTRIBUTION_LEDGER.md` — the PR series: what each contribution
  delivers, its tests, review verdict, and merge commit

## Checks

```bash
pip install -e ".[dev]"
python -m pytest
ruff check src tests && ruff format --check src tests
python -m mypy
python -m build
```
