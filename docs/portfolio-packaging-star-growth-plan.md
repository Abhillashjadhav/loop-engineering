# Portfolio Packaging and Star Growth — Seven-Loop Plan

## Outcome

Increase voluntary GitHub stars by making the five public portfolio repositories easier to discover, understand, run, trust, and recommend.

Stars are treated as the market outcome, not as evidence of engineering quality.

## Portfolio hierarchy

1. **pm-evals** — flagship product and primary acquisition doorway.
2. **loop-engineering** — technical authority and verified-execution proof.
3. **AI-PM-essential-skills** — distribution hub and plugin marketplace.
4. **PM-agent-OS** — broad product-management workflow system.
5. **Linkedin-research-posts** — evidence-grounded authority-content product.

## Loop graph

| Loop | Repository/surface | Locked result | Verification |
|---|---|---|---|
| L1 | Profile + all repos | One coherent portfolio architecture, descriptions, cross-links, and audience mapping | No conflicting hierarchy; every product has one role |
| L2 | AI-PM-essential-skills | Current marketplace becomes the public storefront; old and new identities reconciled | One documented installation path reaches a usable plugin |
| L3 | pm-evals | Outcome-first flagship with a compelling failure-analysis demo | Clean checkout produces a useful report in <=5 minutes |
| L4 | loop-engineering | Concrete hero story showing failure prevention and evidence-backed completion | Synthetic run produces and exposes the evidence pack |
| L5 | PM-agent-OS | Three jobs-to-be-done replace catalogue-first discovery | New user can install safely and choose one workflow without reading all skills |
| L6 | Linkedin-research-posts | Visible sample output and bounded dry-run | Clean checkout produces a review package; no publishing occurs |
| L7 | Portfolio | Discovery, trust, consistency, and clean-checkout gate | All quickstarts pass; links and claims are consistent |

## Metrics

### Primary market outcome

- Baseline total stars across the five repositories: **5** on 2026-07-22.
- Net new total stars after 30 days.
- Net new stars per repository.
- Visitor-to-star conversion when GitHub traffic data is available.

### Leading metrics

- Time to identify the intended user and outcome.
- Time to first successful output.
- Clean-checkout quickstart pass rate.
- Commands required before first value.
- Presence of visible sample output.
- Cross-repository referral paths.
- Release and distribution assets shipped.

### Guardrails

- No artificial star solicitation, purchased stars, coordinated exchanges, or misleading promotion.
- No claim exceeds committed evidence.
- Synthetic and live results remain explicitly separated.
- Existing security, privacy, deterministic tests, and CI gates remain enforced.
- Product simplicity cannot hide material limitations.
- Every independently useful outcome ships through a focused PR.

## Execution policy

- L1 runs first because it locks positioning and prevents portfolio drift.
- L2-L6 may run in parallel only after L1 passes.
- L7 runs after the product loops and creates bounded repair tasks for failures.
- Every loop has at most three repair attempts.
- A loop stops rather than shipping when its quickstart, evidence, privacy, or product-identity gate fails.

## Execution result — 2026-07-22

| Loop | Result | Evidence |
|---|---|---|
| L1 | **PASS** | Profile PR `Abhillashjadhav/Abhillashjadhav#1` merged; one flagship, one technical proof, one distribution hub, and two supporting products are now explicit |
| L2 | **PASS** | `AI-PM-essential-skills#30` merged after PR Quality Gates, Public Surface Validation, and Public Smoke all succeeded |
| L3 | **PASS** | `pm-evals#4` merged after clean-checkout Public Smoke succeeded, including install, deterministic demo, tests, and Ruff |
| L4 | **PASS** | `loop-engineering#22` merged after full CI and Public Smoke succeeded, including synthetic evidence-pack generation |
| L5 | **PASS** | `PM-agent-OS#52` merged after Repository Audit and Public Smoke succeeded, including safe install, overwrite refusal, and force-replace path |
| L6 | **PASS** | `Linkedin-research-posts#16` merged after test and Public Smoke succeeded, including research, draft, review package, privacy, and repository gates |
| L7 | **PASS WITH FOLLOW-UP** | All five clean-checkout gates passed and claims remained bounded; reproducible metadata script added for GitHub descriptions and topics |

## Remaining distribution work

Packaging is now materially stronger, but packaging alone does not create stars. The next bounded phase should measure and improve distribution without weakening trust:

1. Apply the repository descriptions and topics using `scripts/apply_portfolio_metadata.sh --apply`.
2. Publish one evidence-backed launch artifact per flagship, beginning with `pm-evals`.
3. Measure stars by repository at 7-day and 30-day checkpoints.
4. Use GitHub traffic data, when available, to separate a discovery problem from a conversion problem.
5. Create repair tasks only where observed visitor behaviour identifies friction.
