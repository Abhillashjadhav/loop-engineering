# context-audit-harness

Makes the **seven context-engineering inputs** explicit and inspectable on every
LLM call, then deliberately breaks four of them and measures the
**trajectory-score drop** against a clean baseline.

Runnable proof of one idea: **context is the variable, not the model** — and
its corollary, **presence ≠ sufficiency** (an input can be present in context
and still fail to do its job).

## Model in the loop

Claude **inside the Claude Code session** does the generation. **No Anthropic
API key. No metered tokens.**

- Deterministic Python assembles the context, breaks inputs, and scores.
- The generation step = Claude reads the assembled context bundle and writes the
  output; the harness then scores it.
- Locked **prepare / run / report** pattern — LLM judgment isolated to the
  session, never scoring itself (builder–validator separation).

## Domain

A 25-item **home-goods catalog** assistant. Flow per call: user asks → retrieve
from catalog → may call a tool (`check_stock` / `get_price`) → keeps memory
across turns → governed by a hard system instruction → prior tool output feeds
the next step → long history gets compacted.

Anchor system instruction (the checkable "do-not"):

> **Never recommend an out-of-stock item. If stock is unknown, say so.**

## The seven inputs (audited on every call)

1. System instructions
2. Tools the model can call
3. Retrieved knowledge
4. Memory of prior turns
5. User query
6. Outputs of previous tool calls
7. Compaction / summarization

## The four breaks (baseline first, then one break per run)

1. **System instruction present-but-ignored** — the "no out-of-stock" rule sits
   in context; measure whether the model recommends out-of-stock anyway. → input 1
2. **Retrieval gap** — feed a wrong/missing chunk → confident wrong answer. → input 3
3. **Compaction drops a constraint** — the summary loses an earlier commitment →
   agent contradicts itself. → inputs 4/7
4. **Stale prior tool output** — `check_stock` returns stale "in stock" → poisons
   the next recommendation. → input 6

## Metric

**Trajectory score, not pass@1.** Binary checks across the call sequence.
Baseline scores high; each break drops the score in a measured, traceable way.

## Architecture (locked)

- **prepare** (`src/prepare.py`, deterministic): build catalog, context bundle
  (seven inputs), test scenarios, the locked eval checklist.
- **run** (Claude, this session): generate against each assembled context; log
  the trajectory to `runs/`.
- **report** (`src/report.py`, deterministic): score trajectories against the
  locked checklist; emit baseline vs each break with the audit table.
- The eval harness (`eval/`) is **locked** — the thing that generates never
  scores itself.

## Layout

```
.
├── data/    # catalog.json (25 items) + scenarios.json (the 4-turn conversation)
├── src/     # prepare.py, context_bundle.py, harness.py, run_*.py, report.py
├── runs/    # trajectory logs (baseline + 4 breaks) + report.md dashboard
├── eval/    # checklist.json — the LOCKED eval checklist (validator-side)
├── NARRATION.md   # first-person write-up: what was built and what it proves
└── README.md
```

- `src/prepare.py` — catalog + deterministic keyword retrieval.
- `src/context_bundle.py` — the seven-input bundle + Context Audit table (OK/GAP/BROKEN).
- `src/harness.py` — shared scenario loading, honest tool execution, bundle assembly.
- `src/run_baseline.py`, `src/run_break{1..4}.py` — Claude in-session writes the
  assistant turns; each break compromises exactly one input.
- `src/report.py` — deterministic scorer + trace dashboard. Never generates.
- `eval/checklist.json` — six binary checks + per-turn ground truth, **frozen**.

## Run it

```bash
cd src
python3 run_baseline.py        # generate the clean trajectory -> runs/baseline.json
python3 run_break1.py          # ... and each break -> runs/break1.json, etc.
python3 run_break2.py
python3 run_break3.py
python3 run_break4.py
python3 report.py dashboard    # score all five + render the trace dashboard + report.md
python3 report.py baseline     # single-run detail: full Context Audit + per-check results
```

No API key, no network, no paid services — fully deterministic and reproducible.

## Results

Baseline scores a perfect trajectory; each break drops it by exactly one check,
traceable to a single input via the audit row that flips to BROKEN:

| run | score | drop | broken input (cause) | failed check (symptom) |
|---|---|---|---|---|
| baseline | 24/24 = 100% | — | none | none |
| break1 | 23/24 = 96% | -4% | input 1 | C1 |
| break2 | 23/24 = 96% | -4% | input 3 | C4 |
| break3 | 23/24 = 96% | -4% | input 4, input 7 | C5 |
| break4 | 23/24 = 96% | -4% | input 6 | C1 |

**The headline:** break #1 and break #4 produce the *same symptom* (recommend an
out-of-stock item → C1 fails) from *opposite root causes* — break #1 ignored a
truthful rule (row 1 BROKEN), break #4 trusted a lying tool (row 6 BROKEN). The
symptom doesn't tell you where it failed; the Context Audit does. See
[`NARRATION.md`](NARRATION.md) for the full write-up and [`runs/report.md`](runs/report.md)
for the generated dashboard.

## Status

Complete — baseline + four breaks build, run, and score; dashboard and narration
emitted. Builder/validator separation holds: the generator never scores itself.
