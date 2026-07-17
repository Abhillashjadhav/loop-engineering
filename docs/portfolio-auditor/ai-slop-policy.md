# AI-slop verdict policy

Exactly one repository-level verdict per repository:
**`AI_SLOP` · `NOT_AI_SLOP` · `INSUFFICIENT_EVIDENCE`.**

The verdict applies **only to the repository artifact and its accessible
evidence — never to the person who created it.** "AI slop" is an operational
repository-quality label, not a moral or personal judgment.

## Hard `AI_SLOP` requires all of

- confidence **≥ 70** (`hard_verdict_min_confidence`);
- a **recorded counter-evidence review** (what would make this *not* slop, and
  why the evidence still points to slop);
- **material, evidenced signals**, e.g. unsupported claims, generated prose with
  no functioning implementation, duplicated mechanisms, shallow wrappers with no
  differentiated value, no meaningful tests/evals, unverifiable outcomes,
  unfinished journeys presented as complete, or documentation that repeatedly
  contradicts the implementation.

If these are not met, the verdict is **`INSUFFICIENT_EVIDENCE`** (the default
when uncertain), not a soft accusation.

## `NOT_AI_SLOP` evidence

Original mechanisms, coherent architecture, clear product decisions and
trade-offs, functioning end-to-end journeys, meaningful tests/evals, failure
handling, honest limitations, claim-to-evidence traceability, reproducible
setup, careful packaging, demonstrated use over narrative.

## Forbidden sole bases (never sufficient on their own)

writing style · disclosed AI assistance · commit volume · repository size ·
generated-file count · lack of popularity.

Disclosed AI assistance is explicitly **not** penalized. A repository is never
labeled `AI_SLOP` on style or volume alone; such signals may contribute only
alongside material, evidenced quality failures.
