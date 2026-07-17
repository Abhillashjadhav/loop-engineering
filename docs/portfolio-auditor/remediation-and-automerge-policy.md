# Remediation and auto-merge policy

The **finished** auditor may audit, produce a backlog, recommend atomic
remediation PRs, implement policy-safe remediations, open **draft** PRs, run
independent fresh-context review, and — only after every required gate passes —
merge remediation PRs automatically, then re-audit.

> **Scope of auto-merge authority:** `future_remediation_prs_only`. It **never**
> authorizes merging the Portfolio Auditor feature branch itself
> (`never_auto_merges_the_auditor_feature_branch: true`). In V1 all remediation
> runs against sandbox/fixture repositories in dry-run.

## Auto-merge required gates (ALL must pass)

| Gate id | Meaning |
|---|---|
| `within_approved_scope` | change is inside the approved remediation scope |
| `no_unresolved_product_decision_change` | does not alter an unresolved product decision |
| `tests_first_where_applicable` | tests written first where applicable |
| `substantive_ci_green` | substantive CI is green (not a trivial/no-op run) |
| `independent_review_approve` | independent fresh-context review returns APPROVE |
| `no_blocking_finding_remaining` | no blocking security or product finding remains |
| `post_patch_audit_passes` | the post-patch audit passes |
| `bound_to_inspected_commit` | PR is bound to the exact inspected commit |
| `does_not_weaken_gates` | does not weaken tests, evals, evidence, or safety gates |

## Never auto-merged

major architecture rewrites · product-scope changes · business-claim changes
needing user input · destructive archival or repository deletion · repository
consolidation · changes based on insufficient evidence · changes that weaken
validation · changes that hide or delete failed evidence.

## Post-remediation

After any merged remediation PR: re-scan, rerun the affected deep-inspection
checks, verify the original finding, check for regressions, update the
scorecard and dashboard, classify each finding as **FIXED / PARTIALLY_FIXED /
NOT_FIXED / REGRESSED**, record score/verdict changes and the exact remediation
commit, and **never erase the original failed evidence.**
