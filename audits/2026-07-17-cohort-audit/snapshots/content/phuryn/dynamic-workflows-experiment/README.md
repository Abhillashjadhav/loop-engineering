# dynamic-workflows-experiment

The experiment behind the Product Compass article *Dynamic Workflows: The Orchestrator Moved Off the Model*.

It demonstrates one thing: **a dynamic workflow earns its keep when the output of one stage decides the next**, not on a single fan-out (a subagent already does that). The pipeline runs a product-discovery loop end to end:

```
100 interviews  ->  Extract (Haiku, one agent per file)
                ->  Canonicalize (one agent: cluster synonymous needs before counting)
                ->  Score (code: frequency x importance x (5 - satisfaction))
                ->  Ideate (Sonnet) + triage (separate judge)
                ->  Build static HTML prototypes for the top 3 (frontend-design skill)
                ->  Loop: re-run low-confidence extractions and prototypes that don't render
```

## Why synthetic, and why an answer key
We start from the end. `ground-truth/answer-key.md` plants a known set of opportunities with intended scores. We generate 100 interviews that *voice* those opportunities (in story form, never as labels), then run the analysis workflow **blind** and check whether it recovers the planted ranking. Recovery is the proof; real interviews carry the truth.

The interviews are written by **Haiku** (cheap, bounded, repetitive work) via a dynamic workflow that fans out one agent per interviewee. That generator is itself a small dynamic workflow.

## How to run the analysis
You generate the workflow yourself: open the repo in Claude Code and paste `prompts/run-discovery-workflow.md`. Claude writes the harness, runs it blind against `interviews/`, prints the ranked opportunities, and writes prototypes to `outputs/`. See `CLAUDE.md` for the full flow. `example-workflows/` holds reference harnesses (what Claude tends to generate) — read them, don't invoke them.

## Layout
- `CLAUDE.md` — context + how to run, for Claude Code.
- `interviews/` — 100 synthetic transcripts (1-2 pages each). The blind input.
- `ground-truth/` — product, strategy, and the hidden answer key. Never given to the analysis.
- `prompts/` — `generate-interview.md` (generation) and `run-discovery-workflow.md` (paste this to run the analysis).
- `example-workflows/` — reference harnesses: `generate-interviews.js` (the generator that produced `interviews/`) and `discovery-loop.js` (the analysis shape). Not for direct invocation.
- `outputs/` — where your run writes the ranked table + the HTML prototypes. Nothing here is committed.

## Status
100 interviews generated (Haiku, ~2.2M tokens). A 10-interview smoke run recovers the planted #1 need cleanly. Analysis is prompt-driven (see `CLAUDE.md`); budget the full 100 at ~2M tokens.

MIT. A local experiment, not a product.
