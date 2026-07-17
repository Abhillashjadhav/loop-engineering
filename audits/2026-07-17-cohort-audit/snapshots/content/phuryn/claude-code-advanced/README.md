# Claude Code Advanced — Power Skills for PMs

Companion repo for the **Claude Code Power Skills for PMs** session (Product Compass, [AI-Native PM roadmap](https://www.productcompass.pm/p/ai-native-pm-roadmap)). It extends the base session template with a working agent-memory system, loop demos, and a dynamic-workflows experiment.

The example persona: a PM on **Google Maps**. All product data in the examples is fictional — the structure is the lesson.

## What's inside

| Path | What it is |
| --- | --- |
| [CLAUDE.md](CLAUDE.md) | A 5-line import stub — all instructions live in AGENTS.md so the same setup works in both Claude Code and Codex |
| [AGENTS.md](AGENTS.md) | The real instruction file: strategic context, memory protocol, communication style, quality bar, subagent routing, tools |
| [SUBAGENTS.md](SUBAGENTS.md) | Model routing (Haiku/Sonnet/Opus/Fable), the consult-up pattern, delegation economics |
| [knowledge/](knowledge/INDEX.md) | **Agent memory in the Open Knowledge Format style**: plain markdown, an INDEX.md at every level, facts → hypotheses → rules with promotion on evidence. Start at the root INDEX |
| [docs/strategy.md](docs/strategy.md) | The example product strategy (Google Maps) referenced from AGENTS.md |
| [.claude/skills/](.claude/skills/) | Project skills (canonical copies; mirrored to `.agents/skills/` by a PostToolUse hook so Codex sees them too) |
| [.claude/hooks/](.claude/hooks/) | Session-start hook example (remote-session context injection) |
| [examples/loops/](examples/loops/README.md) | Autonomous loops: the `/goal` template, loop-vs-schedule, and a runnable demo with a [burnstop](https://github.com/phuryn/burnstop) budget cap |
| [examples/ingestion/](examples/ingestion/README.md) | A raw pilot readout to feed the memory system — watch a hypothesis get promoted to a rule live |
| [examples/dynamic-workflows/](examples/dynamic-workflows/README.md) | The [dynamic-workflows-experiment](https://github.com/phuryn/dynamic-workflows-experiment): 100 synthetic interviews, a blind discovery pipeline, provable against a planted answer key |
| [tools/](tools/) | Scheduled unattended run example (`gmail_linear_daily.cmd`), a Reddit API utility, the skills sync script |

## Quick start

1. Clone, open in VS Code with the Claude Code extension (or the CLI).
2. Copy `.env.example` to `.env` and fill in keys only if you want the Reddit tool — everything else works without it.
3. Say: *"Read knowledge/INDEX.md and tell me what you'd load for a task about restaurant discovery."* Watch it route instead of bulk-reading.

## How the memory system works (60 seconds)

- Every folder has an `INDEX.md`. The agent reads the map first and loads only the 1-2 domains a task needs.
- Each domain holds the same trio: `knowledge.md` (facts), `hypotheses.md` (suspected patterns + evidence log), `rules.md` (confirmed, applied by default).
- A hypothesis confirmed by 3+ independent data points becomes a rule. A rule contradicted by new data is demoted back — with the counter-example on record.
- The protocol the agent follows lives in [AGENTS.md § Memory](AGENTS.md). The system compounds: same agent on day 100, very different memory.

**Watch it learn (ingestion):** the system learns from data passing through a session, not from you editing it. `users/hypotheses.md` H1 sits at 2 of 3 confirmations, and [examples/ingestion/](examples/ingestion/README.md) holds a raw pilot readout that contains its third. Say:

```
Ingest examples/ingestion/pilot-readout-2026-07.md per AGENTS.md § Memory:
file facts, update hypothesis evidence logs, and promote or demote anything
that crosses the bar.
```

Expected: one promotion fires (H1 → `users/rules.md`, evidence trail attached), and the readout's stray signals get filed across two other domains — the agent's judgment call, argued per the protocol.

## Further reading (Product Compass)

- [The Intent Engineering Framework for AI Agents](https://www.productcompass.pm/p/intent-engineering-framework-for-ai-agents)
- [Loop Engineering for PMs](https://www.productcompass.pm/p/loop-engineering-for-pms)
- [Claude Dynamic Workflows for PMs: The Ultimate Guide](https://www.productcompass.pm/p/claude-code-dynamic-workflows)
- [PM Brain OS: The Second Brain for Product Managers](https://www.productcompass.pm/p/pm-brain-os) · advanced version of the memory pattern: [phuryn/pm-brain](https://github.com/phuryn/pm-brain)
- [The Ultimate Guide to Claude Fable 5](https://www.productcompass.pm/p/claude-fable-5-guide)
