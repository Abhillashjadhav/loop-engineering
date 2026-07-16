# Decisions log

One line per meaningful architectural choice. Format: "YYYY-MM-DD: Chose X over Y because Z."

- 2026-07-16: Repurposed this repo from the job-search-agent seed content to Loop Engineering V1 on branch `claude/loop-engineering-v1-j513lb`, because the build specification defines this repository's shape; the seed content remains intact on `main`.
- 2026-07-16: PRD derived from the authoritative build specification instead of the 5-question interview because the spec carries locked, pre-approved product decisions (PD-01..PD-08) and the run is autonomous.
- 2026-07-16: Chose stdlib + PyYAML + jsonschema over any framework because file-backed JSON/JSONL/YAML state is a locked constraint and minimal dependencies keep mypy-strict and offline CI tractable.
- 2026-07-16: Chose dataclasses + explicit enum state machines over an ORM/state library because task transitions must be auditable and testable deterministically.
- 2026-07-16: Chose atomic file replacement (`tempfile` + `os.replace`) for all state writes because crash-safe resume is a completion condition.
- 2026-07-16: Verification pass conditions are declarative dicts (file_exists / file_contains / json_valid / digest_matches / min_count) evaluated by the verifier from the filesystem, never from executor statements, to enforce the no-self-verification guardrail structurally.
- 2026-07-16: GitHub data access is behind a `GitHubDataSource` protocol with a fixture-backed implementation; live audit of the two named subjects is out of scope for this session because GitHub access here is scoped to this repository only — recorded as a blocked item, not simulated.
- 2026-07-16: Six-run stability variants parameterize ordering/stance/blindness deterministically; disagreements are reported per-run, never averaged.
