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

## Independent review (PR #14) — outcome

Fresh-context read-only review returned REQUEST_CHANGES with 3 blocking
findings; all fixed with regression tests (`tests/chief_of_staff/test_review_fixes.py`):

1. `free_gaps` matched events by start-date string, so overnight/offset
   events were treated as free time → now interval-intersection in absolute
   time.
2. Non-ISO deadline cues ("12/1", "tomorrow", "friday") were stored raw and
   compared lexicographically → now normalized to ISO at extraction,
   deterministically against the run clock; unparseable cues store None.
3. The prior-checkpoint prohibited-action guard was dead code (never loaded,
   literal snake_case match) → checkpoint-latest.json persisted + loaded each
   run, token-based matching that fires on natural language.

Also fixed from the review: non-actionable (blocked/waiting/inbox/done)
tasks no longer consume focus blocks (finding 5), and executed safe actions
now carry the generated artifact as evidence instead of a bare "performed"
claim (finding 7 — honesty rule).

## Follow-up backlog (non-blocking review findings, deliberately deferred)

- finding 4: buffer also before the first block of a gap / before meetings
- finding 6: `_merge` should keep max(urgency/impact/strategic_value/energy)
  and non-empty blocked_by/description from the losing twin
- finding 8: load `operating-contract.yaml` (and a private per-user contract)
  instead of hardcoded `OperatingContract()` defaults
- finding 9: blocked/waiting categorization should win over keyword bands;
  extend displacement detection beyond admin-vs-job
- finding 10: fail loudly (or mark source UNAVAILABLE) when a data dir/source
  file is missing instead of silently returning []
- finding 11: privacy root check by path components; PrivacyViolation on
  symlink escape; mkdir after ignore check
- finding 12: `_WAITING` should not capture stopwords ("waiting for the…")
- finding 13: real midday slipped/new-urgent diffing; call `carried_forward`
- plus: cross-run register persistence, live adapters (separate PRs)

## Cross-run register persistence (follow-up PR)

`store.py` — append-only JSONL journal at `runs/private/cos/state/journal.jsonl`
(fail-closed private boundary via `private_path`). Content-addressed idempotent
ingestion; per-event sha256; torn-tail recovery (crash-safe resume) vs
fail-loud middle corruption; terminal-state protection (DONE/DROPPED never
silently reactivate; new evidence → INBOX); DONE requires evidence; optimistic
conflict detection (`expected=` → ConflictError); checkpoint + artifact
history; schema versioning with v0→v1 migration and newer-version refusal.
Runner takes `store=`; CLI persists by default (`--no-persist` to opt out).
18 planted-failure tests in `tests/chief_of_staff/test_store.py`.

## Google Calendar live read-only adapter (follow-up PR)

`adapters/google_calendar.py` — CalendarAdapter-protocol implementation over
the Calendar v3 REST API, least-privilege `calendar.readonly` scope, token +
config under `config/private/` (fail-closed guard). LIVE is claimed only
after a real read executes; no write path exists (`create_focus_block`
raises). Injectable GET-only transport; typed redacted errors (auth/
permission/rate-limit/unavailable/malformed — no token, body, or event
content in any message). Normalization: pagination + cross-page dedup,
all-day, overnight, DST offsets, recurrence identity, cancelled excluded,
transparent events not busy (busy-aware free_gaps), untitled placeholder,
deterministic ordering, retrieval provenance on every item. CLI: extended
`status`, new `check-calendar` (read-only), `--calendar auto|live|fixture`
(auto = live only when configured; the label always says which). 27
tests-first cases in `tests/chief_of_staff/test_google_calendar.py`.

## Independent review (PR #18) — outcome

Fresh-context read-only review of the calendar adapter returned
REQUEST_CHANGES with 2 blocking findings at `440db59`, both PoC-confirmed
and fixed with regression tests at `a0a8f8f`:

- finding 1: a repeated `nextPageToken` looped forever — now each calendar
  tracks seen tokens and a `MAX_PAGES` cap; a repeat or overflow raises
  `MalformedResponseError` instead of hanging.
- finding 2: a token file with the `scope` field omitted passed the scope
  check (fail-open) — now an undeclared scope raises
  `CalendarPermissionError` (fail-closed), same as a too-broad scope.

Round 2 returned APPROVE at `a0a8f8f`. GitHub CI then failed on the fresh
checkout only: `git check-ignore` cannot match the dir-only pattern
`/config/private/` for a path whose directory does not exist, so a fresh
clone crashed on read-only `status` — a genuine latent bug masked locally
by the dirs existing. Fixed at `18f4d82` (`_is_git_ignored(..., as_dir=True)`
retry on the parent; hermetic CLI tests; fresh-checkout regression test).
Because that delta touches the safety-critical privacy guard, a dedicated
fresh-context delta review re-verified it: **APPROVE stands at `18f4d82`** —
fail-closed preserved (missing boundary still raises; tracked or
index-present files always refuse), original bug reproduced against the old
code, new regression test fails on the old implementation, all gates green.

Residual (documented, non-blocking): a deliberate `.gitignore`
restructuring using a contents glob plus a negation
(`/config/private/*` + `!config/private/foo.json`) could let `private_path`
pass an untracked-but-trackable file. It cannot arise from accidental
drift, is independently blocked here by the `**/private/` catch-all, is
caught by `test_no_private_paths_are_tracked_in_repo` the moment such a
file is tracked, and self-heals to fail-closed once tracked. Follow-up
hardening candidate: also require the file-level check to pass when the
file exists.
