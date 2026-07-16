# Live audit runbook — one manual step, then fully automated

Repository analysis for the two live subjects is blocked in the build session
(all 16 in-session access routes exhausted — see `ACCESS-BLOCKED.md`).
Identity is already verified (`identity-evidence.md`); `examples/subjects.yaml`
carries the verified attributes. One step outside that session completes the
data handoff:

## Step 1 — harvest (any machine with GitHub access, ~3 minutes)

```bash
git clone https://github.com/Abhillashjadhav/loop-engineering && cd loop-engineering
pip install pyyaml
python audits/2026-07-16-live-audit/harvest_snapshots.py \
    --subjects examples/subjects.yaml \
    --out audits/2026-07-16-live-audit/snapshots
git add audits && git commit -m "audit: live snapshots" && git push
```

The script paginates the complete public repo listing per subject, enriches
each record with commit/contributor counts, preserves every raw response with
sha256 + retrieval timestamp under `snapshots/evidence/`, cross-checks the
harvested count against the profile's `public_repos`, and **verifies its own
output loads through the engine's data source** before exiting (it also
supports `--verify` to re-check and `--self-test` for an offline layout check,
which passes in CI conditions: "self-test: PASSED").

Unauthenticated rate limit is 60 req/h — export `GITHUB_TOKEN` (read-only
public scope) if either subject has many repositories.

## Step 2 — tell the audit session "snapshots are pushed"

The session then runs, in order: per-repo signal inspection (observable
signals only, evidence-cited, absent-not-guessed), then

```bash
loop-engineering audit-github --subjects examples/subjects.yaml \
    --fixtures audits/2026-07-16-live-audit/snapshots
```

which executes the locked methodology end to end: identity gate → inventory →
ten-dimension rubric scoring → Loop 1 per task → Loop 2 per stage → Loop 3
independent evidence verification → Loop 4 six analysis variants → End-to-End
Goal Reviewer (Gate A/B) → Accuracy Evidence Pack under
`outputs/github-authority-audit-live/` with repository scorecards, all eight
score fields, both portfolio weightings, the subject comparison, six-run
comparison, unresolved uncertainties, and the accuracy rationale.

Hard rules that remain in force: AI-share is reported only as
0–25 / 25–50 / 50–75 / 75–100 / INSUFFICIENT_EVIDENCE; negative
classifications require slop ≥ 70 AND confidence ≥ 70 AND a recorded
counter-evidence review; no private-intent claims; repos lacking recorded
signals classify INSUFFICIENT_EVIDENCE rather than being guessed.
