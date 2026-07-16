# Cursor Layer PM Toolkit

The companion repo for [Is the Chatbox the Wrong Interface for AI?](https://www.news.aakashg.com/p/cursor-ai) by Aakash Gupta.

Google and Farza shipped the same idea the same week: AI that lives at the cursor instead of in a chatbox. This toolkit helps you find where your product needs cursor-layer thinking and prototype it.

## Quickstart

- **Day 1 (5 min):** Read the three stages below. Pick one AI feature on your roadmap and place it at Stage 1, 2, or 3.
- **Day 1 (30 min):** Fill out `audit/cursor-layer-audit.csv` for your product. Use `audit/worked-example.md` if you get stuck.
- **Week 1 (20 min):** Run one of the three prototypes in `/prototypes`. Pick the one that matches the highest-frequency row in your audit.
- **Week 2:** Bring the audit's top 3 rows + the design spec to your next planning meeting. You'll walk in with a feature list, target stages, and an estimated time-saved-per-quarter for each.

## The Three Stages (at a glance)

| Stage | Where the AI lives | What the user does | Example |
|---|---|---|---|
| **1 — Destination** | Separate app/tab | Leaves work, describes screen, loses place | ChatGPT in a browser tab |
| **2 — Embedded** | Sidebar/panel inside the product | Still selects context, types, reads in a panel | Notion AI, Copilot sidebar |
| **3 — Cursor Layer** | At the point of interaction | Speaks or points, AI sees screen, responds inline | Clicky, Google Magic Pointer |

Higher isn't always better. Deep research, long-form generation, and exploratory chat belong at Stage 1. The audit helps you find features that are stuck at the *wrong* stage, not push everything to Stage 3.

## What's Inside

### `/audit`
- **cursor-layer-audit.csv** — Three-tab template: Context Switch Map, Overhead Inventory, Eight-Second Opportunity Log
- **worked-example.md** — Filled-out audit for a fictional B2B SaaS (TaskFlow), including computed scores and the resulting roadmap recommendation
- **scoring-rubric.md** — Stage 1/2/3 diagnostics plus the prioritization formula

### `/prototypes`
- **01-screen-aware-assistant.md** — Cowork workflow: vision-powered assistant that answers questions about what's on your screen
- **02-context-switch-tracker.md** — Routine: monitors and logs where users leave your product for quick answers
- **03-micro-interaction-agent.md** — Claude Code skill: eight-second help moments inside your codebase

### `/design-spec`
- **cursor-layer-design-spec.md** — The four-component framework (Screen Context, Voice Input, Spatial Response, Agent Handoff) plus the Stage-to-Component map

## Before You Run This at Work

Two of the three prototypes touch data that may be sensitive. Per-prototype callouts live inside each file, but the short version:

- **Prototype 1** asks you to screenshot dashboards and product UI into Claude. If your product surfaces customer data, check your DLP and AI-use policies before piping production screenshots anywhere.
- **Prototype 3** reads files from your local codebase. Fine for personal repos and side projects. For employer codebases, confirm Claude Code is approved.
- **Prototype 2** only reads public posts (Reddit, X, G2). No internal data leaves your machine.

## Requirements

- Claude Pro, Max, Team, or Enterprise (for Cowork and Routines)
- Claude Code (for the skill prototype)
- The audit, scoring rubric, and design spec are platform-agnostic. Prototype 1 (Cowork) is best on macOS today. Prototype 3 (Claude Code skill) works on macOS, Linux, and Windows — paths called out per-prototype.

## License

[MIT](./LICENSE). Customize everything. Credit appreciated but not required.
