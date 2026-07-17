# stockscope — a winner-signal backtest harness that refuses to fool you

This repo answers one question before any capital or any live trading system gets built:

> Do a small set of proven signals — measured strictly point-in-time, on a survivorship-free universe — separate future *winners* from *losers* in US Nasdaq healthcare and technology stocks, with an edge over the base rate that survives costs and holds across multiple years?

The answer the harness gives is a verdict: **GO** (the signals earned the right to drive a live system), **MARGINAL**, or **KILL** (they didn't — stop here, having spent a small harness instead of a full build and real money).

On its first end-to-end run against real SimFin, FRED, and price data, it returned **KILL**. That result is the point of this README — not because the signals are worthless, but because **the verdict is honest about what the data can and cannot support**, and producing that honesty is the entire engineering problem.

---

## Why a KILL is the result worth showing

It is trivial to write a backtest that prints an exciting number. It is hard to write one that tells you when your evidence is too thin to trust — and then refuses to bless it. This harness is built to do the second thing.

The first real run scored two signals (momentum and quality) across 2018–2022 on a 28-ticker universe. Both came back blocked:

| signal | mean lift | net of 4pp haircut | rank-IC | held in | sample floor |
|---|---|---|---|---|---|
| momentum | −0.005 | −0.045 | +0.071 | 0 of 5 years | LOW (min arm 30 < 300) |
| quality | −0.128 | −0.168 | −0.072 | 0 of 5 years | LOW (min arm 16 < 300) |

Read the per-year detail and the reason becomes obvious. Momentum's best year (2021, +0.179 lift) carries a confidence interval of **[−0.214, +0.607]** — it spans zero by a wide margin. With ~28 names over 5 years, *nothing in this sample could ever reach significance.* The harness says so directly: `sample floor not met`.

So the KILL is not a statement that momentum and quality don't work in the real world. It is a statement that **this sample — small, survivor-only, five independent year-slices — physically cannot support a GO**, and the harness was engineered to detect exactly that and stop. A naive backtest would have pooled the 280 overlapping monthly observations into a tight, false-looking confidence interval and printed GO. This one de-overlaps to 5 real slices, applies a survivorship/cost haircut, enforces a sample-size floor, and declines.

That discipline is the artifact.

---

## The three non-negotiables (enforced by tests, not by trust)

Most backtests die from one of three quiet errors. Each is closed here by an automated check that is *designed to fail* if the protection is removed:

1. **No peeking (look-ahead leakage).** Every datum carries a `knowledge_date` — the day it actually became public. All data access flows through a single function, `get_data(field, ticker, as_of)`, that returns only rows where `knowledge_date <= as_of`. No signal reads raw data directly. A leak test proves the chokepoint is non-vacuous: it plants a future-dated row in a deliberately leaky store and confirms the test catches it. Filing lags are modeled explicitly (a Q4 result with period-end 2020-12-31 but filed 2021-02-26 is correctly invisible on a 2021-01-31 decision date).

2. **Survivorship-free universe.** Using today's survivors inflates returns by 1–4%/yr and can reverse conclusions. The universe at any historical date is meant to include companies since delisted, merged, or bankrupt; a known-delisted ticker must appear in its historical universe or the test fails. *(See the honest limitation below — this is the part the current run does not yet fully satisfy.)*

3. **Two-arm comparison.** Every signal is judged on `P(winner | signal fired)` versus the unconditional base rate, with the losers — the same-signal non-winners — explicitly counted. A winners-only view is structurally forbidden. The stats engine is calibration-tested: fed synthetic data with a known injected lift of 0.20, it recovers 0.203; fed a true-null dataset, it correctly reports zero lift.

---

## How it works

A plain-Python `run.py` orchestrates four components. There is **no LLM in the run path** — an LLM orchestrator would add cost and non-determinism to what is fundamentally a numeric experiment. (The harness is free to run; the only judgment calls happen at design time, in code.)

1. **Data-Integrity** — pulls point-in-time data (SimFin bulk fundamentals and sector classification; FRED for macro; yfinance/Stooq for prices), runs fail-loud schema and coverage checks, and quarantines bad rows naming the exact ticker and field rather than dropping them silently. SimFin is the sole fundamentals + sector source: SEC EDGAR's per-ticker API throttles at universe scale (it left the quality signal n/a for ~1,800 names), whereas one bulk SimFin download covers them all. This is a coverage fix, not a survivorship fix — the universe stays survivor-limited (§2.2).
2. **Signal-Compute** — computes the locked signals deterministically. Pure, testable math, each component covered by decimal-exact golden cases.
3. **Backtest/Stats** — labels winners (beat the Nasdaq Composite by ≥15pp over 12 months), builds the two-arm comparison, computes lift, confidence intervals, rank-IC, and walks forward year by year with purge/embargo to prevent overlapping labels from inflating significance.
4. **Reviewer** — a PR agent that enforces every eval gate on each commit against the architecture spec.

The signals under test are those with genuine cross-decade evidence: price momentum, earnings-estimate revision breadth, and quality/profitability (used as a failure filter) — plus a macro risk-off gate. (Insider cluster buying was retired when EDGAR/Form 4 was removed; see the limitations below.)

---

## What this run does *not* prove (the honest limitations)

I would rather state these plainly than have them found:

- **The universe was 28 hand-picked survivors.** The point-in-time membership adapter that would inject delisted names is still a stub, so this run is survivorship-*aware in design* but survivorship-*biased in data*. Any verdict on this universe is a verdict about the pipeline's correctness, not about the strategy's real edge. A meaningful GO/KILL needs the full universe including delisted tickers.
- **The sample is far too small for significance.** Five year-slices, ~16–30 names per arm, against a ~300/arm floor. This is why everything reads LOW. It is not a tuning problem; it is a data-volume problem.
- **Insiders were removed entirely.** The Form 4 signal was sourced only from SEC EDGAR, which needs hundreds of fragile per-filing fetches and throttles at universe scale. When EDGAR was dropped in favour of SimFin as the sole fundamentals + sector vendor, no free survivorship-clean Form 4 feed remained, so the signal was retired. The live core is now momentum + quality.
- **Revision breadth is forward-only.** Historical analyst-estimate snapshots are paywalled, so this signal can be tracked going forward but not backtested historically on free data.

These are the `$0-data` asterisks. The harness surfaces them in every report's coverage and honesty sections rather than hiding them.

---

## What's been validated

- The full pipeline runs end-to-end on real SimFin / FRED / price data and emits a coherent, evidence-graded verdict.
- The no-peek chokepoint, filing-lag logic, survivorship test, two-arm structure, and stats calibration each pass with a *non-vacuity proof* — a deliberately planted failure that confirms the guard actually fires.
- The verdict logic will not round up: a signal that misses any gate is blocked, with the specific blocking reason printed.

## Next phase

A meaningful multi-year verdict requires, in order: a survivorship-free point-in-time universe including delisted names; and a wider universe across more years. Until then, the result stands as what it is — proof that the machine grades evidence honestly, including when the honest grade is *not enough*.

---

*Sources: SimFin (bulk fundamentals + sector classification; free API tier, key via `STOCKSCOPE_SIMFIN_API_KEY`), FRED, yfinance/Stooq. No LLM in the run path.*
