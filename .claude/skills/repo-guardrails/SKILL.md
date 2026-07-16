---
name: repo-guardrails
description: Standing engineering guardrails for the Dreamjob job-search agent — the concrete mistakes made in past sessions (across multiple threads) and the rule that prevents each one from recurring. Use this skill BEFORE editing any pipeline code under agent/, adding or changing a job source, changing scoring/thresholds, writing a loop that does I/O per item, calling any external API/actor, editing the GitHub Actions workflow, updating tests, or committing pipeline changes. Also use whenever the user points out something that "we already discussed" or "keeps happening." This exists so lessons are read from the repo, not re-derived from scratch each thread (which is itself one of the logged mistakes). The resume-specific gate lives in the separate `resume-integrity` skill — use both when a change touches resumes. Skip only for trivial, non-pipeline edits (docs typos, comments).
---

# Repo Guardrails — don't repeat these

This is the running ledger of real mistakes made building this agent, with the
rule that stops each one. It is committed to the repo on purpose: the same
lessons were independently re-derived in more than one session, which wasted
work. **Read it before pipeline work; add to it whenever a new mistake costs a
round-trip.** Keep entries concrete (what broke, why, the rule).

## How to use this
- Before the work surfaces listed in the description, skim the relevant section.
- When the user says "we discussed this" / "you did this again" → the rule
  almost certainly already lives here or belongs here. Find it or add it.
- When you fix a new class of mistake, append it here **and**, if it's
  programmatically checkable, wire a check (don't rely on memory).

---

## 1. Parallelize divisible I/O work — never serial (standing policy)
**Mistake:** scoring called the `claude` CLI one candidate at a time, serially,
over ~290 candidates. The run was force-cancelled at the 60-min CI cap
mid-call (run #27765752429) and produced nothing.
**Rule:** any divisible, I/O-bound workload (LLM calls, HTTP fetches, per-item
subprocess) runs in **parallel lanes, ≥10 by default**, never sequentially.
The scorer uses a `ThreadPoolExecutor`; default is 10 (`SCORER_MAX_WORKERS`,
clamped 1–16). Preserve output order/count (write results by index) and let a
per-item failure fall back gracefully instead of sinking the batch. When you
add any new per-item loop, ask first: "can this be lanes instead of a line?"

## 2. Make the workload fit the budget — don't just raise the timeout
**Mistake:** CI timeout was bumped 30 → 60 to accommodate heavier runs; the
run still blew past 60 because the real problem was serial work, not the cap.
**Rule:** when work outgrows the time budget, **fix the throughput first**
(parallelize, batch, pre-filter), then set the timeout as a *backstop* with
headroom — not as the fix. (Now 120 min, with 10-lane scoring meant to finish
in ~10.)

## 3. External APIs accept only their documented values — verify, don't invent
**Mistake:** set Apify `datePosted: "r172800"` (48h). The actor silently
rejects non-preset codes and returned 0 jobs → run #57 hard-failed.
**Rule:** when a field is an enum/preset (date codes, payload keys, slugs),
validate against the **actual accepted set** and guard in code. Valid Apify
date presets: `r86400` / `r604800` / `r2592000` only — enforced by
`VALID_DATE_POSTED` in `agent/sources/apify_linkedin.py`. The actor wants
`limit`, not `rows`; `datePosted` is the seconds code, not `"Past Week"`.
Same lesson bit Workday: 6/12 tenant slugs were wrong (`site` mismatch) and
silently returned 0 — verify slugs against the live endpoint (`--verify`).

## 4. Surface silent degradation loudly — empty/cheap output is a valid, invisible state
**Mistake:** scoring ran `[heuristic-only]` for many runs because
`CLAUDE_CODE_OAUTH_TOKEN` held an **API key** (`sk-ant-api03-…`) instead of an
**OAuth token** (`sk-ant-oat01-…`). It "worked" (no exception) but produced
crude keyword scores. Separately, `skip_apify=True` once produced a clean run
with zero real output.
**Rule:** a pipeline that produces empty/degraded output must say so **in the
output** — subject-line flags (`[heuristic-only]`, `[LOW_COVERAGE]`,
`[no-apify]`, …), a Drift/error-notes section, and the halt artifacts
(`RUN_FAILED.md` / `RUN_ANOMALY.md` / `RUN_REFUSED.md` via
`agent/invariants.py` + `agent/anomaly.py`). Never let "no exception" stand in
for "it worked." Token types matter: `oat01` = Max-plan OAuth (what we want);
`api03` = paid API key (fallback only). Verify via the workflow's "Diagnose
secrets" step, which prints length + 13-char prefix (never the value).

## 5. One source of truth — keep code constants in sync with the written rules
**Mistake:** the apply floor drifted to `FIT_THRESHOLD = 70` in code while
CLAUDE.md Hard Rule 1 said 80; the bump cap in code (+12 max) lagged the doc.
**Rule:** thresholds/caps live in one place and are referenced everywhere
(`scorer.FIT_THRESHOLD`, `NEAR_MISS_FLOOR`, `BUMP_CAP`; `gmail_only_scorer`
derives from them). When you change a rule, change it in the code constant
**and** CLAUDE.md in the same commit. Current: floor 80, near-miss 60–79,
bump cap +20 (stacked, gated on genuine documented adjacency — never inflate).

## 6. Update tests in the same change that changes the contract
**Mistake:** LinkedIn queries were expanded 10 → 35 and the payload contract
changed (`rows`→`limit`, removed `APIFY_RUN_URL`), but `tests/test_apify_linkedin.py`
still asserted the old values — left red on main.
**Rule:** when you change a count, constant, payload shape, or public symbol,
fix its tests in the **same** commit. A red suite that "isn't my change" is
still your problem to flag or fix.

## 7. Prefer aggregators over per-portal connectors
**Mistake/temptation:** chasing per-company career sites for coverage.
**Rule:** the leverage is the paid LinkedIn/Indeed actors that ingest
everything; enumerating per-company ATS endpoints is tech debt that doesn't
move recall. Confirm the strategic approach before building a new source. (The
exception that earned its place: Workday CXS, because it's one free no-auth
endpoint covering a whole class of big employers invisible to the others.)

## 8. When "completeness" is the goal, verify the actual ceiling
**Mistake:** per-query `limit` was hard-capped at 50, silently under-sampling
while the fetch "succeeded."
**Rule:** for a completeness goal, check the real ceilings — per-query `limit`,
pagination depth, budget caps (`max_jobs_per_run`) — not just that the call
ran without error. A capped sweep looks successful while missing most of the
catalogue.

## 9. Don't re-ask a decided question; don't re-litigate a decision
**Mistake:** re-confirming things the user already settled (e.g. "open the PR",
"keep MJ Internet excluded", fit floor) — wasted turns.
**Rule:** if the user already answered, act. Decided facts so far:
MJ Internet Pvt Ltd stays excluded from resumes (it's the user's own company,
but excluded by choice); apply floor is 80; scoring parallelism default is 10
lanes. Don't reopen these without a new reason.

## 10. Fix recurring bugs at the single chokepoint + add a programmatic gate
**Mistake:** the pre-Amazon "Product" title bug recurred across sessions
because the rule lived only in chat while a hardcoded table re-broke it.
**Rule:** kill a recurring class of bug at the one place all paths funnel
through (`patch_profile_for_skill_md`), then back it with an executable gate
(`agent/check_resume_integrity.py`) so it can't silently return. Memory is not
a control. (Full detail in the `resume-integrity` skill — use it for any
resume/profile change.)

## 11. Persist what matters — ephemeral state silently degrades
**Mistake:** resume PDFs were `.gitignore`d and never persisted; `seen_index`
once degraded to a single-day window, resurfacing the same roles daily.
**Rule:** anything the next run depends on must be committed (PDFs under
`outputs/*/resumes/` are tracked; `seen_index.jsonl` is persisted back to main
by the workflow). On a fresh container nothing survives unless pushed.

## 12. Overly broad bump keywords inflate fits — exhaust credits on false positives
**Mistake:** Run #60 produced **109 fits** (target: 1–10) because the heuristic
adjacency bump in `agent/scorer.py` checked for bare `'platform'` as a keyword.
"Platform" appears in virtually every senior PM job description, so any near-miss
Director PM role (natural score ~70) got a +10 bump → 80 → "fit". 109 resume
generations then drained the Claude Max plan credits, causing 8 PDFs to fail and
the integrity invariant to halt the run. The same issue was in the LLM CLI prompt:
"Baseline 10 for any real PM role" encouraged the LLM to score generously.
**Rule:** bump keywords must be *specific* compound phrases, not single generic
terms. Specifically: `'developer platform'`, `'ml platform'`, `'ai platform'`,
`'genai platform'`, `'data platform'`, `'platform engineering'` are fine;
bare `'platform'` is banned from the bump trigger. The LLM prompt must say
explicitly that generic 'platform' or 'product management' does NOT qualify for
adjacency, and include a calibration line: "A typical day produces 1–10 genuine
fits; if you score >15 roles as 80+, recalibrate."
**Check:** After scoring, log the fit count to trajectory.jsonl. If fits > 25,
the anomaly detector should flag it — that many fits in one day is a scoring bug,
not a good day.

---

## Maintenance
When a new mistake costs a round-trip, add a numbered entry here (mistake →
why → rule) in the same session you fix it, and wire a check if it's
mechanically verifiable. This file is the antidote to re-deriving the same
lessons in the next thread.
