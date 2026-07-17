# Portfolio Auditor — use-case config

Config and the digest-locked product contract for the GitHub Portfolio Auditor
(V1). Code lives in `src/loop_engineering/use_cases/portfolio_auditor/`; design
docs in `docs/portfolio-auditor/`.

## Files

- `contract.yaml` — the **immutable, digest-locked `ProductDecisionContract`**.
  It pins the verdict vocabularies, AI-slop policy, business-accuracy scale,
  prioritization formula, remediation/auto-merge policy, metrics, safety rules,
  and the integration boundary. Do not hand-edit; change it via
  `portfolio_auditor.contract.amend(...)` (approver + reason → new version).
- `strategic.yaml` *(added in M3)* — the operator-supplied strategic/marketable
  repository list + allowlist. Imported via config, **never** via source code.

## Verify the contract

```python
from loop_engineering.use_cases.portfolio_auditor import contract as pc
c = pc.load_default()          # loads + verifies schema and digest
pc.auto_merge_required_gates(c)  # the 9 locked auto-merge gates
```

## Locked guarantees (V1)

- Verdicts judge the **repository artifact**, never the person.
- **Dry-run by default**; no real repository is touched until sandbox safety
  tests pass and an explicit allowlisted, non-dry-run audit is requested.
- Business/product accuracy uses **repository evidence only** in V1.
- Auto-merge authority is for **future remediation PRs only** — never the
  auditor feature branch.
