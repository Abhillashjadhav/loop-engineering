# Audit lifecycle

A Portfolio Auditor run is a deterministic pipeline over file-backed state.
Every stage persists provenance; any hard stop writes a `BLOCKED.md` naming the
exact unblock requirement (reusing the circuit-breaker convention). Nothing
interrupted or unverified is ever delivered as success.

## Stages

```
CONFIGURED        strategic list + allowlist + audit mode loaded and validated
   │              (dry-run default; real repos untouched until sandbox tests pass)
   ▼
BROAD_SCANNED     read-only mechanical scan of every in-scope repository (M2)
   │
   ▼
SELECTED          risk score + strategic priority → deep-inspection set (M3)
   │
   ▼
DEEP_INSPECTED    evidence-backed dimension inspection of selected repos (M4)
   │
   ▼
SCORED            deterministic per-dimension scores + confidence (M4/M6)
   │
   ▼
CLASSIFIED        AI-slop verdict + recommendation per repository (M5)
   │
   ▼
REPORTED          portfolio JSON/Markdown, scorecards, backlog, evidence index (M6)
   │
   ▼  (optional, sandbox-only in V1)
REMEDIATION_PLANNED → REMEDIATION_PR(draft) → REVIEWED → CI → GATED_MERGE (M7)
   │
   ▼
RE_AUDITED        re-scan + finding-closure classification + before/after (M8)
```

## Audit modes

- **quarterly** — full portfolio cadence.
- **on_demand** — a manual audit of a named repository set.
- **post_remediation** — a focused re-audit bound to a merged remediation commit.

## Invariants

- **Dry-run by default.** No real repository is read or written until the
  sandbox safety tests pass; writes require an explicit, non-dry-run run against
  an allowlisted repository.
- **Provenance at every stage.** owner, name, visibility, inspected commit,
  audit id, rubric/scanner/prompt/model versions, commands executed, evidence
  references, inspection depth, strategic priority, confidence, verdict, and the
  reason for the verdict are all persisted.
- **Only verified counts.** A stage that cannot be verified does not advance the
  pipeline; it blocks with a recorded reason.
- **Evidence is append-only.** Original (including failed) evidence is never
  erased — re-audits add new records beside it.
