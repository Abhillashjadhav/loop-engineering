"""GitHub Portfolio Auditor V1.

An isolated use-case capability inside Loop Engineering ("Production
Engineering OS"). It inspects accessible public and private GitHub
repositories and recommends, per repository, whether to FIX / SHOWCASE /
CONSOLIDATE / REBUILD / KEEP_AS_IS — evidence-backed, confidence-gated, and
with an explicit repository-level AI-slop verdict (AI_SLOP / NOT_AI_SLOP /
INSUFFICIENT_EVIDENCE).

Fairness is locked: the verdict applies only to the repository artifact and
its accessible evidence, never to the person who created it. All judgment
signals are recorded by the Claude/agent layer; the Python runtime only scores
them deterministically (no model SDK/API calls here) and keeps file-backed
JSON/JSONL/YAML state.
"""
