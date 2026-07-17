# Threat model

## Assets

- Private-repository **source, secrets, names, and configuration**.
- **Audit integrity** — evidence, scores, and verdicts must be trustworthy.
- **Merge authority** — the finished auditor can open/merge remediation PRs.

## Trust boundaries

- **Python runtime** — offline, deterministic, no network, no model calls. Only
  scores recorded signals. Cannot exfiltrate or mutate remote state by itself.
- **Skill/agent layer** — performs fetches and records signals; the only place
  with network/model access. Its outputs are treated as untrusted input and are
  schema-validated before scoring.
- **GitHub API** — least-privilege token; write actions are gated and, in V1,
  sandbox/dry-run only.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Private data leaked into a public report | `origin`-based redaction of private origins; private repo names never in public reports; secret scanning before any output |
| Destructive change to a repository | destructive-action blocking; no archival/deletion via auto-merge; dry-run default; explicit allowlist |
| Incorrect automatic merge | 9 required gates, all must pass; independent fresh-context review; bound-to-inspected-commit; blocking-finding gate |
| Evidence tampering to obtain a preferred verdict | digest-locked contract; append-only evidence; original failed evidence never erased; scoring is deterministic from recorded signals |
| Prompt/model drift changing verdicts run-to-run | persisted rubric/prompt/model versions; repeated-run consistency tests; deterministic scoring core |
| Supply-chain / unsafe dependency in an audited repo | security & dependency-integrity dimension; lockfile + reproducible-install checks reported as findings |
| Rate-limit abuse / cost blowout | rate-limit handling, retry/resume, cost controls, scan/deep-inspection duration metrics |
| Secrets committed in the auditor itself | secret scanning in CI; no credentials in fixtures |

## Non-negotiables

Honesty over helpfulness — a `BLOCKED` report with the exact unblock
requirement is always preferable to an invented result. No private-intent
claims. No exact AI-authorship percentages. The feature branch is never
auto-merged.
