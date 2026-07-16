# Dreamjob-agent — Week {ISO_WEEK} Digest
**Period:** {START_DATE} → {END_DATE} · **Generated:** {GEN_DATE}

## TL;DR
- Volume: {N_RAW} raw → {N_VERIFIED} verified → {N_FITS} ≥80% fits → {N_RESUMES} resumes
- Honesty: {HONESTY_SCORE}/5 mean · {N_FABRICATED} fabricated · {N_P0} P0 alerts
- Calibration: Apply-rate at 80+ = {APPLY_RATE_80}% · divergence median = {DIV_MEDIAN} pts
- Top finding: {ONE_LINE}

## 1. Trajectory health
| Axis | Week | 4-wk mean | Δ | Status |
|---|---|---|---|---|
| Coverage | {X}/5 | {Y}/5 | {Δ} | {🟢🟡🔴} |
| Efficiency | {X}/5 | {Y}/5 | {Δ} | {🟢🟡🔴} |
| Rule compliance | {X}/5 | {Y}/5 | {Δ} | {🟢🟡🔴} |
| Recovery | {X}/5 | {Y}/5 | {Δ} | {🟢🟡🔴} |
| Honesty | {X}/5 | {Y}/5 | {Δ} | {🟢🟡🔴} |

Regressions: {LIST or "none"}

## 2. Output divergences (|judge − agent| > 10)
| Role | Company | Agent | Judge | Δ | Why |
|---|---|---|---|---|---|
| {ROLE} | {CO} | {A} | {J} | {Δ} | {ONE_LINE} |

## 3. Bullet quality
Total bullets: **{N_BULLETS}** · Defensible: {N_DEF} ({PCT}%) · Reframed: {N_REF} ({PCT}%) · **Fabricated: {N_FAB} ({PCT}%) ← target: 0**

Fabrication examples (if any):
> Role: {ROLE} · "{TEXT}" · Why: {RATIONALE}

## 4. Calibration drift
Apply-rate by score bucket:
| Bucket | n | Apply | Skip | Rework | Apply % |
|---|---|---|---|---|---|
| 90–100 | {N} | {N} | {N} | {N} | {%} |
| 80–89 | {N} | {N} | {N} | {N} | {%} |
| 70–79* | {N} | {N} | {N} | {N} | {%} |
| 60–69* | {N} | {N} | {N} | {N} | {%} |

*gap-only surface, not resumes

Slope: {monotonic|inverted|noisy} · Dimension diagnosis: {LIST or "no bias"}

## 5. ATS quality
| Metric | Median | p10 | Regenerations |
|---|---|---|---|
| Parseability | {X} | {X} | {N} |
| Keyword coverage | {X} | {X} | — |

## 6. Proposed adjustments (require approval)
Reply `/approve P{N}` or `/reject P{N}`. Defer = no action.

### P1 — {TITLE}
Type: {threshold|rubric|profile|skill rule}
Rationale: {2-3 lines, evidence-backed}
Min-labels gate: {satisfied|NOT — defer}

```diff
- {OLD}
+ {NEW}
```
- [ ] Approve
- [ ] Reject
- [ ] Defer

## 7. What's queued for Monday auto-commit
Approved proposals ship in a PR Monday 09:00 IST. Profile changes wait for manual merge.

## 8. Anomalies & notes
- {Free-text from judge}

---
*Eval mode: {observe-only|active}. Labels collected: {N}. Calibration unlocks at 30.*
