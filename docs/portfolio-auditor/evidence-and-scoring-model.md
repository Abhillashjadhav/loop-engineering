# Evidence, scoring, and confidence model

## Evidence

Every material finding and every verdict must carry evidence. Evidence reuses
the shared `EvidenceItem`, whose **`origin`** field is the independence key.

- **Valid evidence kinds:** repo file+line, commit, test, CI workflow, release
  artifact, executed command, evaluation report, browser trace, screenshot,
  deployment proof, architecture document, issue/PR history.
- **Corroboration:** a material claim needs ≥ 2 *independent* origins; a
  high-impact claim needs ≥ 3. Two items corroborate only when their `origin`
  values differ. **A README is not corroboration for its own claims.**
- **Absence claims** (e.g. "no tests") require recorded `SearchCoverage`
  (queries + scope + whether coverage was complete). Incomplete coverage means
  the absence is *not asserted as verified* — it may still be a scoring input,
  but it is disclosed, never certified.

## Finding record (required fields)

`finding_id · repository · dimension · evidence · confidence · severity ·
affected_capability · reasoning · remediation_recommendation`

Severity ∈ {BLOCKING, HIGH, MEDIUM, LOW, INFO}. `is_blocking` ⇔ BLOCKING.

## Confidence

- Integer **0–100**, clamped on construction.
- **High-confidence floor = 70.**
- **A numeric score never overrides a material high-confidence finding.**
  `must_surface(finding)` returns true for any BLOCKING/HIGH finding at or above
  the floor; such findings are always reported regardless of prioritization
  rank (`prioritization_score` orders work, it does not gate disclosure).

## Dimension scoring

- Each assessment dimension scores **0–100**, computed deterministically from
  recorded signals — never from an executor's self-assessment.
- When the recorded evidence does not support a score, the dimension floors to
  **INSUFFICIENT_EVIDENCE** rather than inventing a number.

## Business-accuracy grades

Business/product claims are graded on the locked scale
**PROVEN / LIKELY / NOT_PROVEN / CONTRADICTED / INSUFFICIENT_EVIDENCE** using
the evidence chain: claimed problem → target user → implemented capability →
demonstrated journey → measurable value → repository evidence. **Absence of
evidence is not automatically falsehood** (that is `NOT_PROVEN` /
`INSUFFICIENT_EVIDENCE`, not `CONTRADICTED`).

## Prioritization

`Priority = strategic_importance * severity * authority_impact * confidence /
remediation_effort` (effort > 0 enforced). Priority order, high to low:
marketable → GenAI-authority → high technical/incident risk → large
claim-to-evidence gap → high AI-slop risk → strong reuse potential.
