# Cohort audit runbook — decisions + one harvest step, then automated

Goal `github-authority-audit-cohort-2026-07` (contract:
`examples/goal.cohort.yaml`, subjects: `examples/subjects.cohort.yaml`).
The completed 2026-07-16 audit is reused as evidence for aakash-gupta and
shubham-saboo and is never modified.

## Step 0 — operator decisions (before harvesting)

1. **Private flagships.** `loop-engineering` and `production-engineering-os`
   are not publicly visible (identity-evidence.md). The audit is public-
   artifacts-only: as long as they are private they are invisible — they will
   not appear in the inventory and cannot be flagships. Make them public
   before the harvest if they should count.
2. **Abhillash person→login link.** No public channel currently links to
   github.com/Abhillashjadhav. Adding the GitHub URL to his public LinkedIn
   (or any publicly-controlled page) creates the independent identity origin;
   otherwise the identity claim rests on profile-field matches only and
   Loop 3 will report it at one independent origin.
3. **Aishwarya Srinivasan** stays IDENTITY_UNRESOLVED_FOR_GITHUB_AUDIT
   unless a channel she controls names a specific account (evidence doc has
   the reversal condition).

## Step 1 — harvest (any machine with GitHub access)

```bash
git pull
export GITHUB_TOKEN=<read-only token>   # REQUIRED: ~6 API calls per original repo
# reuse the completed audit's snapshots for the two repeated subjects:
mkdir -p audits/2026-07-17-cohort-audit/snapshots
cp -r audits/2026-07-16-live-audit/snapshots/. audits/2026-07-17-cohort-audit/snapshots/
python audits/2026-07-17-cohort-audit/harvest_snapshots.py \
    --subjects examples/subjects.cohort.yaml \
    --out audits/2026-07-17-cohort-audit/snapshots \
    --skip-logins aakashg,Shubhamsaboo
git add audits examples && git commit -m "audit: cohort snapshots" && git push
```

Notes:
- The cohort copy of the harvest script also records `description` and
  `topics` per repo (used by the deterministic top-10 selection) and supports
  `--skip-logins` for the two reused subjects.
- Portfolio sizes for the technical cohort are large (eugeneyan ~70+,
  chiphuyen, hamelsmu 100+ repos); expect a few thousand API calls — fine
  under the authenticated 5,000/h limit; the script paces itself.
- The script must end `verify: PASSED`. A MISMATCH/FAILED line means re-run
  in place (safe).

## Step 2 — tell the audit session "cohort snapshots are pushed"

The session then runs, in order:

1. `select_deep_inspection()` (src/…/github_authority_audit/deep_inspect.py)
   per subject — deterministic top-10 by current activity, public prominence
   (selection visibility only), code surface, and AI/ML/evals/agents/product
   relevance; config-designated flagships always included; every repo not
   selected is labeled `deep_inspected: false`, never silently skipped.
   Flagships: Abhillash — PM-agent-OS, pm-evals, rag-eval-harness (+
   loop-engineering, production-engineering-os only if made public);
   Paweł — pm-skills + formula picks; cohort B — formula picks.
2. Inspector agents record judgment signals for the selected repos from the
   saved snapshot content only (same rules as the completed audit: omission
   means not-observed, ≥3 distinct non-readme evidence origins, mandatory
   counter-evidence review on negative reads, mechanical signals untouchable).
3. Merge + validate (per the completed audit's merge_inspections.py pattern,
   adapted to stamp `deep_inspected` on every record), then:

```bash
loop-engineering audit-github \
  --subjects examples/subjects.cohort.yaml \
  --fixtures audits/2026-07-17-cohort-audit/snapshots-inspected \
  --goal-file examples/goal.cohort.yaml
```

which executes identity gate → inventory → rubric → Loops 1-4 (six
variants) → E2E reviewer (Gate A/B) → Accuracy Evidence Pack. The skill
layer then produces the cohort report answering, separately: A strongest
technical depth, B best usable products, C strongest distribution, D best
technical-work→public-authority conversion, E where Abhillash is genuinely
ahead, F where he is behind, G product vs packaging/distribution gaps,
H three highest-leverage actions — public artifacts only, no private-intent
or private-competence inference, AI-share as ranges only, popularity never
as technical quality.

Hard rules in force throughout: identical to the completed audit (PD-01…
PD-08); repos lacking recorded signals classify INSUFFICIENT_EVIDENCE rather
than being guessed; not-deep-inspected repos still get mechanical-signal
scoring but their labels disclose the shallower evidence base.
