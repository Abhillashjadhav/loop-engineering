# Accuracy Evidence

Generated: 2026-07-16T17:23:06.859686+00:00

## Original goal and expected output

**Goal (github-authority-audit-live v1):** Using publicly available evidence only, determine whether the public GitHub portfolios of Aakash Gupta and Shubham Saboo demonstrate substantive GenAI technical proficiency, meaningful human/product/engineering reasoning, education/curation strength, distribution strength, heavily AI-assisted but useful creation, or shallow/templated work — without inferring private intent or exact authorship.


**Expected deliverables:** cross-subject comparison, final answer with per-subject verdicts, person-level assessments, repository scorecards

**Contract digest:** `sha256:2ec3ff28101b4aa97283e396a88e6bfd10bfc31da562a0db29e6f235eb0e7d60`

## Process completeness (Gate A)

Verdict: **COMPLETE**

- PASS — every_required_task_verified (10 task(s) terminal)
- PASS — verified_status_backed_by_loop1_result
- PASS — repairs_reverified (0/0 repair task(s) reverified)
- PASS — all_required_loops_ran
- PASS — run_not_interrupted (run status: RUNNING)
- PASS — evidence_files_and_digests_exist (evidence files: 7, verified tasks missing digest: [])

## Autonomous task completion

- Planned tasks completed autonomously: 100.0%
- Human interventions: 0

## First-pass verification

- First-pass task verification rate: 100.0%
- Average repair attempts per task: 0.0

## Claim evidence coverage

- Material claims: 73
- Independently supported: 39 (53.42%)
- Unsupported (excluded from all percentages): ['aakash-gupta-aakashg-no-tests', 'aakash-gupta-awesome-ai-pm-no-tests', 'aakash-gupta-claude-design-pm-toolkit-no-tests', 'aakash-gupta-claude-routines-and-agents-pm-pack-no-tests', 'aakash-gupta-cups-task-no-tests', 'aakash-gupta-cursor-layer-pm-toolkit-no-tests', 'aakash-gupta-hermes-pm-toolkit-no-tests', 'aakash-gupta-pm-claude-code-setup-no-tests', 'aakash-gupta-pm-claude-skills-no-tests', 'aakash-gupta-pm-github-starter-kit-no-tests', 'aakash-gupta-pm-github-workflow-repo-no-tests', 'aakash-gupta-pm-planning-system-no-tests', 'aakash-gupta-pm-prompt-library-no-tests', 'aakash-gupta-product-growth-team-os-no-tests', 'shubham-saboo-ai-breakup-recovery-agent-no-tests', 'shubham-saboo-ai-linkedin-post-scanner-no-tests', 'shubham-saboo-awesome-ai-agent-prompts-no-tests', 'shubham-saboo-awesome-llm-apps-no-tests', 'shubham-saboo-BERT_Sentiment_Analysis-no-tests', 'shubham-saboo-chatgpt-discord-no-tests', 'shubham-saboo-customer-center-analytics-nlp-no-tests', 'shubham-saboo-docarray-nocode-no-tests', 'shubham-saboo-gemini-artboard-no-tests', 'shubham-saboo-gpt3_book_sandbox-no-tests', 'shubham-saboo-gpt3_sandbox-no-tests', 'shubham-saboo-javascript_wizard-no-tests', 'shubham-saboo-jina_finetuner_notebooks-no-tests', 'shubham-saboo-openclaw-vertexai-memorybank-no-tests', 'shubham-saboo-Portfolio-no-tests', 'shubham-saboo-repotovideo-no-tests', 'shubham-saboo-Shubhamsaboo-no-tests', 'shubham-saboo-Valentines_Message_Generator-no-tests', 'shubham-saboo-weekly-report-analysis-no-tests', 'shubham-saboo-zero-shot-image-classifier-no-tests']
- Claims with visible source conflict: ['aakash-gupta-awesome-ai-pm-classification', 'aakash-gupta-cups-task-classification', 'aakash-gupta-pm-claude-code-setup-classification', 'aakash-gupta-pm-claude-skills-classification', 'aakash-gupta-pm-github-starter-kit-classification', 'aakash-gupta-pm-github-workflow-repo-classification', 'aakash-gupta-pm-planning-system-classification', 'aakash-gupta-pm-prompt-library-classification', 'aakash-gupta-product-growth-team-os-classification', 'shubham-saboo-ai-breakup-recovery-agent-classification', 'shubham-saboo-awesome-ai-agent-prompts-classification', 'shubham-saboo-awesome-llm-apps-classification', 'shubham-saboo-chatgpt-discord-classification', 'shubham-saboo-customer-center-analytics-nlp-classification', 'shubham-saboo-gpt3_book_sandbox-classification', 'shubham-saboo-openclaw-vertexai-memorybank-classification', 'shubham-saboo-Portfolio-classification']

## Four-loop results

- loop1_task: 10/10 passed
- loop2_drift: 4/4 passed
- loop3_evidence: 39/73 passed
- loop4_stability: 1/1 passed

## Six-run agreement / disagreement

- Variants compared: 6
- Stable findings: 74
- Unstable findings (disagreement preserved): 0
- Unresolved: 2

## Goal drift

- Drift: 0.0% (guardrail < 5%)
- Orphan tasks: none
- Uncovered requirements: none

## End-to-end goal-match score

- Score: **91/100** → **GOAL_MATCH**
  - goal_coverage: 100.0
  - output_contract: 100.0
  - north_star_outcome: 100.0
  - scope_discipline: 100.0
  - evidence_quality: 53.4
  - uncertainty_disclosure: 100.0
  - actionable_conclusion: 100.0

## North Star outcome

- Baseline manual minutes: 720.0
- Human active minutes: 0.0
- Goal successfully verified: True
- Estimated minutes saved: 720.0

## Exclusions and limitations

- (contract exclusion) private intent, private contributions, or exact human/AI authorship
- (contract exclusion) non-public data sources of any kind
- (contract exclusion) judgments about the person rather than the public artifacts
- analysis is limited to public artifacts at retrieval time; private contributions are invisible to this audit
