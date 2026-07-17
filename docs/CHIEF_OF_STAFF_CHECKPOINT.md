# Personal Chief of Staff — build checkpoint

Status: **MVP complete and green.** Branch `claude/personal-chief-of-staff-mvp`.
This file is the resume anchor per the operating mode; nothing here claims work
that is not present and tested.

## Completed (all tested, all green)

- **Private-data boundary**: `data/private/`, `runs/private/`, `config/private/`
  git-ignored; `privacy.py` guard resolves private writes and **fails closed**
  if the boundary is missing or a path escapes. Test proves no private path is
  tracked.
- **Data model** (`models.py`): Goal, Task (+ TaskSource provenance),
  CalendarItem, DecisionCheckpoint, ActionProposal — closed StrEnums.
- **Personal Operating Contract** (`contract.py` + committed
  `operating-contract.yaml`): 7 locked goals, priorities, rejected ideas,
  terminology, project boundaries, 12 prohibited actions.
- **Adapters** (`adapters/`): protocols + fixture/manual-import + Unavailable;
  every adapter labeled LIVE/FIXTURE/MANUAL_IMPORT/UNAVAILABLE with setup hints.
- **Discovery** (`discovery.py`): explicit extraction rules; deadlines never
  invented; informational email → no task; stale GitHub PR → inbox/inferred.
- **Register + dedup** (`registry.py`): one source-backed register; dedup
  merges duplicates preserving all provenance.
- **Prioritization** (`prioritize.py`): locked order; confidence-discounted;
  recency/ease never raise priority.
- **Scheduling** (`schedule.py`): real free time only, protects meetings,
  buffers, no overlap, overflow reported.
- **Safe execution + approval** (`execute.py`): safe actions auto-run;
  prohibited actions fail closed; focus blocks need one approval.
- **Context-drift + checkpoints** (`checkpoint.py`): goal/scope/decision/
  evidence checks, priority-displacement + rejected-idea detection.
- **Briefs** (`briefs.py`): morning/midday/evening, deterministic, clock bound
  to run metadata (no `datetime.now()`).
- **Dashboard** (`dashboard.py`): self-contained local HTML, every task line
  shows source + confidence; written to the private dir.
- **CLI** (`cli.py`): `chief-of-staff ingest|tasks|brief|schedule|
  approve-schedule|execute-safe|checkpoint|dashboard|status`.
- **Demo** (`use_cases/personal-chief-of-staff/demo/`): synthetic, all 9
  required scenarios; demonstration test proves each capability.

## Tests

- Chief-of-staff suite: 33 tests (discovery/registry/priority, privacy,
  schedule/execute/drift, determinism/north-star, demonstration).
- Full repo: **160 passed** (136 baseline + 24 new files) · ruff clean ·
  `mypy --strict` clean (57 files) · `python -m build` OK.
- Planted failures covered: invented deadline, task without source, duplicate
  commitment, low-value outranking interview, meeting overlap, block without
  approval, email-sent-instead-of-drafted, private data committed, completion
  without evidence, uncertainty→fact, rejected idea resurfacing, stale GitHub
  task active, task from informational email, prohibited action auto-executed.

## What is live vs fixture vs manual vs unavailable

Every adapter in the MVP runs in **FIXTURE** mode against committed synthetic
data (or **MANUAL_IMPORT** when `--data` points at a private export dir). No
live integration is faked. Live connectors are seams with exact setup
instructions in the README and `status` command. ChatGPT/Claude context is
**MANUAL_IMPORT** only — no direct API access is claimed.

## Resume / next steps (not yet done)

- Wire live adapters (Google/Gmail/GitHub/Drive) behind the existing protocols
  using tokens under `config/private/` — drop-in, no runtime change.
- Persist the register across runs (currently rebuilt each run from sources);
  add an append-only private task-state file under `runs/private/`.
- Midday "new urgent since morning" diffing (currently the hook exists but the
  demo has a single snapshot).

Resume command:

```bash
git checkout claude/personal-chief-of-staff-mvp
python -m pytest tests/chief_of_staff -q
loop-engineering chief-of-staff dashboard --run-id resume
```
