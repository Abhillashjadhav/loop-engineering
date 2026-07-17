# Acceptance criteria — GitHub Portfolio Auditor V1

V1 is complete only when every criterion below holds. Each maps to the
milestone that satisfies it and to how it is verified (deterministic tests
unless noted). This is the labeled acceptance-criteria artifact for the product
contract; the measurable targets live in the contract `metrics` section.

| # | Criterion | Milestone | Verified by |
|---|---|---|---|
| 1 | Broad scanning works against deterministic fixtures | M2 | scanner tests over fixture repos |
| 2 | High-risk repositories are correctly selected for deep inspection | M3 | selection ranking tests (planted risk) |
| 3 | Deep findings cite evidence (required fields present) | M4 | rubric tests assert evidence on every finding |
| 4 | Business claims are evaluated using repository evidence only | M4 | business-accuracy tests (PROVEN…INSUFFICIENT) |
| 5 | AI-slop verdicts are evidence-backed and confidence-gated | M5 | planted slop / false-positive / consistency tests |
| 6 | Portfolio dashboard data is generated | M6 | report tests (JSON + dashboard-ready data) |
| 7 | Prioritized remediation backlog is produced | M6 | backlog schema + ordering tests |
| 8 | Sandbox remediation PRs work | M7 | dry-run PR orchestration tests |
| 9 | Independent review and CI gates work | M7 | gate evaluation truth-table tests |
| 10 | Approved sandbox PR auto-merge works | M7 | auto-merge gate tests (all 9 gates) |
| 11 | Post-remediation re-audit detects fix/regression | M8 | closure classification tests |
| 12 | Private evidence remains protected | M2–M6 | redaction tests (no private origin/name in public output) |
| 13 | Repeated runs are materially consistent | M5/M9 | repeated-run consistency tests |
| 14 | Dogfood and planted-failure tests pass | M9 | each planted defect detected by its gate |
| 15 | Final draft PR is independently approved and green | Final | review + CI on the feature→main draft PR |
| 16 | The feature PR remains unmerged | Final | draft PR left open, not merged |

## Milestone-level acceptance (applied to every milestone PR)

A milestone PR may merge into `feature/github-portfolio-auditor-v1` only when:
red tests were committed first; the implementation is minimal and complete;
`pytest`, `ruff`, `ruff format --check`, and `mypy --strict` are green;
`python -m build` succeeds at milestone boundaries; an independent
fresh-context review returns APPROVE with no unresolved blocking finding; and
no gate was weakened to pass.
