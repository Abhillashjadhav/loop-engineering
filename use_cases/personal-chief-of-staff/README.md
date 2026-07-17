# Personal Chief of Staff (private use case)

A personal operating system that connects goals, commitments, projects,
calendar, communication, execution, and follow-up — so nothing important is
forgotten and high-value work gets done. Built as a reusable Loop Engineering
use case; **no personal data is ever committed to git**.

## What it does

1. **Discovers** commitments, tasks, deadlines, blocked and forgotten work
   from Calendar, Gmail, GitHub, Drive, chat/project context, and manual entry.
2. **Consolidates** them into one **source-backed task register** — every task
   keeps its exact source excerpt, origin (explicit/inferred), and confidence.
3. **Prioritizes** by the locked model (external deadlines → job search →
   product completion → speaking/distribution → blocked/waiting → admin).
   Recency and ease never raise priority.
4. **Schedules** realistic focus blocks in *actual* free time (protects
   meetings, adds buffers, never overlaps, reports overflow).
5. **Creates focus blocks only after one explicit approval.**
6. **Executes safe actions** (drafts, briefs, issue proposals, reminders,
   interview prep). Send/forward/cancel/merge/publish/apply **fail closed** —
   blocked without explicit approval, regardless of priority.
7. **Protects context** with a locked Personal Operating Contract and
   drift checks; writes a decision checkpoint each evening close.
8. **Generates morning / midday / evening briefs** — deterministic, every line
   traceable to its source.

## Privacy (the load-bearing guarantee)

All personal content lives only under git-ignored roots: `data/private/`,
`runs/private/`, `config/private/`. The `privacy.py` guard resolves every
private write and **fails closed** if the `.gitignore` boundary is missing or
a path escapes the private roots. A test asserts no private path is ever
tracked.

## Run the demo (synthetic, safe to commit)

```bash
pip install -e ".[dev]"
loop-engineering chief-of-staff status              # adapter modes + setup hints
loop-engineering chief-of-staff tasks               # prioritized, source-backed
loop-engineering chief-of-staff brief morning       # (also midday | evening)
loop-engineering chief-of-staff schedule            # proposed focus blocks
loop-engineering chief-of-staff approve-schedule    # ONE approval → creates blocks
loop-engineering chief-of-staff execute-safe        # safe actions only
loop-engineering chief-of-staff dashboard           # writes runs/private/.../dashboard.html
loop-engineering chief-of-staff checkpoint          # decision/context checkpoint
```

Determinism: `--day`, `--as-of`, `--run-id` fix the clock; identical inputs
produce byte-identical briefs, dashboard, and run JSON. No `datetime.now()`.

## Real data

Point `--data <dir>` at a **private import directory** (e.g.
`data/private/import/`) holding the same JSON shapes as
`use_cases/personal-chief-of-staff/demo/`. Adapters are honestly labeled:

| Adapter | MVP mode | To go LIVE |
|---|---|---|
| Google Calendar | FIXTURE | OAuth `calendar.readonly` + `calendar.events`, token in `config/private/` |
| Gmail | FIXTURE / MANUAL_IMPORT | OAuth `gmail.readonly` + `gmail.compose` (compose = **drafts only**) |
| GitHub | FIXTURE | `GITHUB_TOKEN` (read scopes) — open PRs, review requests, issues |
| Google Drive | FIXTURE / MANUAL_IMPORT | OAuth `drive.readonly`; export docs to `data/private/` |
| ChatGPT / Claude context | MANUAL_IMPORT | export conversations/checkpoints to `data/private/chat_context/` — **no direct API access is claimed** |
| Manual tasks | MANUAL | dictate/enter into `manual.json` |

Live connectors are seams: the fixture/manual adapters implement the exact
same protocol, so wiring a real client is a drop-in with no runtime changes.

## Guardrails (enforced by tests)

No task without a source · inferred tasks labeled with confidence · deadlines
never invented · no external action without approval · no duplicate
commitments (dedup preserves all provenance) · no private data committed · no
scheduling beyond free time · no calendar block without approval · no false
completion claims (completion needs evidence) · rejected ideas can't resurface
· prohibited actions fail closed · **no important commitment disappears
between ingestion and the brief** (north-star guard).
