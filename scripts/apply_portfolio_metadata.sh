#!/usr/bin/env bash
set -euo pipefail

OWNER="${OWNER:-Abhillashjadhav}"
APPLY=false

if [[ "${1:-}" == "--apply" ]]; then
  APPLY=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--apply]" >&2
  exit 2
fi

gh auth status >/dev/null

update_repo() {
  local repo="$1"
  local description="$2"
  shift 2
  local topics=("$@")

  echo
  echo "$OWNER/$repo"
  echo "  description: $description"
  echo "  topics: ${topics[*]}"

  if [[ "$APPLY" != true ]]; then
    return
  fi

  gh api --method PATCH "repos/$OWNER/$repo" \
    -f "description=$description" >/dev/null

  local topic_args=(
    --method PUT
    "repos/$OWNER/$repo/topics"
    -H "Accept: application/vnd.github+json"
  )
  for topic in "${topics[@]}"; do
    topic_args+=( -f "names[]=$topic" )
  done
  gh api "${topic_args[@]}" >/dev/null
}

update_repo \
  "pm-evals" \
  "Trace-based LLM evaluation for product managers: plain-English rubrics, judge calibration, failure clustering, and release reports." \
  "llm-evaluation" "product-management" "llm-as-judge" "ai-quality" "evals" "python-cli"

update_repo \
  "loop-engineering" \
  "Deterministic runtime for locked goals, atomic execution, independent verification, bounded recovery, and evidence-backed completion." \
  "agentic-workflows" "verification" "autonomous-agents" "reliability" "evaluation" "python"

update_repo \
  "AI-PM-essential-skills" \
  "Installable Claude Code plugins for AI product evaluation, model routing, guarded loops, and MCP migration decisions." \
  "claude-code" "ai-product-management" "agent-skills" "evals" "mcp" "automation"

update_repo \
  "PM-agent-OS" \
  "Evidence-aware product-management skills and reviewer agents for discovery, strategy, build, launch, and iteration." \
  "product-management" "claude-code" "agent-skills" "ai-product" "product-strategy" "evals"

update_repo \
  "Linkedin-research-posts" \
  "Local evidence-backed LinkedIn research and drafting workflow with provenance, deterministic gates, and human approval." \
  "content-workflow" "linkedin" "provenance" "human-in-the-loop" "ai-writing" "privacy"

if [[ "$APPLY" == true ]]; then
  echo
  echo "Portfolio metadata updated."
else
  echo
  echo "Dry run only. Re-run with --apply to update GitHub descriptions and topics."
fi
