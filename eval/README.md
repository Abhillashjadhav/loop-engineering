# Dreamjob-agent Evaluation Harness

Keeps the autonomous job-search agent honest, calibrated, and improving via daily artifact capture, weekly LLM-as-judge eval, and approval-gated calibration.

## Design principles
1. Honesty over coverage. A fabricated bullet is P0.
2. Observe before correct. First 4 weeks = observe-only, no auto-changes.
3. Human-in-the-loop for change. All adjustments require user approval.
4. Calibration from behavior (Apply/Skip/Needs-rework labels), not opinion.
5. Drift kills trust. Drift signals block the daily email.

## Daily artifact capture
- `outputs/{date}/trajectory.jsonl` — every tool call
- `outputs/{date}/candidates.json` — all scored jobs
- `outputs/{date}/resumes/*.pdf` — tailored resumes for ≥80%
- `outputs/{date}/ats_reports/*.json` — parseability + keyword coverage
- `outputs/{date}/briefs/*.md` — daily brief, gap analysis, crisp answers, interview prep
- `outputs/{date}/daily_metrics.json` — funnel volumes, latency, errors
- `outputs/applications.jsonl` (append-only) — user labels

## Weekly cycle
Runs Sunday 20:00 IST via Claude Code Routine.

### Task A — Trajectory eval (per day, 1–5 each axis)
Coverage, Efficiency, Rule compliance, Recovery, Honesty.
Honesty=1 if any fabricated bullet detected (no exceptions).

### Task B — Output audit (per ≥80% role)
Independent fitment scoring; flag if |judge−agent|>10.
Bullet labels: defensible / reframed / fabricated.
ATS sanity recheck. Brief quality 1–5.

### Task C — Feedback calibration
Apply-rate by score bucket, calibration slope, dimension diagnosis, threshold recommendation.

## Weekly digest with user approval
Output: `eval/eval_results/{ISO-week}/digest.md` — emailed + committed as PR.
User approves/rejects each proposal via `/approve P{N}` or `/reject P{N}`.
Approved changes auto-commit Monday 09:00 IST as a PR. Profile changes never auto-merge.

## Drift detection (blocks daily send)
| Check | Threshold | Action |
|---|---|---|
| Trajectory honesty | <4/5 | Block email; review-required notification |
| Fabricated bullet | any | Block email; quarantine resume |
| Score divergence ≥80% role | >15 | Block email; flag role |
| ATS parseability | <85 | Regenerate (max 2); else block role section |
| Empty output | true | Send "low-yield day" notice |

## Calibration loop (after 30+ labels AND 4+ weeks elapsed)
- Apply-rate(70–79) ≥60% → propose threshold = 75
- Skip-rate(80–85) ≥60% → propose threshold = 85 OR rubric reweight
- Needs-rework rate ≥30% → propose resume-rule additions

All proposals require approval. Threshold changes never auto-apply.

## Safe defaults
- Observe-only mode for first 4 weeks
- Threshold changes blocked until 30+ labels
- Profile/skill changes never auto-applied
- Kill switch: `eval/PAUSE` file (presence-only) halts all eval runs

## File structure
```
eval/
├── README.md
├── judge_prompt.md
├── digest_template.md
├── calibration.py
├── eval_results/{ISO-week}/{digest, calibration_proposals, approved_changes}
└── metrics/{trends.json, {date}/daily_metrics.json}
```
