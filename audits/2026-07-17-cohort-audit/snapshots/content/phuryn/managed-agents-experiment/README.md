# Managed Agents Experiment

A firsthand, reproducible comparison of **"managed agents" vs running the agent loop yourself**, across **Google, Anthropic, and OpenAI** — plus a Gemini↔Anthropic format translator and a portability demo (one agent definition running on multiple runtimes).

Run 2026-06-01 by [Paweł Huryn](https://www.productcompass.pm). Every claim is backed by the run logs in [`data/`](data/). Inspect the artifacts, don't trust screenshots.

> **TL;DR** — All three now expose a persistent agent/workflow you invoke by ID over REST (yes, OpenAI too: `POST /v1/workflows/{id}/run`). So I benchmarked each managed runtime against running the same loop on my own machine. The surprise wasn't that managed costs more. It's that "managed" charges for three completely different things: **Google taxes the sandbox** (~5.3×, even on a task that runs no code), **Anthropic taxes ~nothing** (~1.2×, caching absorbs it), **OpenAI taxes the code** (≈ local on reasoning tasks, +$0.03 flat container fee only when it runs code). Same agent, same tasks, 108 runs, all logged. The portable constant across all of it is the agent definition.

## First: "managed agent" means three different things

This is the part most comparisons skip. The providers are not offering the same thing.

| Provider | What "managed" actually is |
|---|---|
| **Google** — Managed Agents (`/v1beta/interactions`) | A real managed runtime. You register an agent; Google provisions a Linux sandbox and runs the **entire multi-step loop** server-side (reason → call tool → run code → observe → repeat → answer). One request, they do every step. Persistent agents, sessions, environments. |
| **Anthropic** — Managed Agents (`/v1/agents` + `/v1/sessions`) | Also a real managed runtime. A container per session, the full loop on Anthropic's orchestration layer, streamed events. Plus success-criteria graders, a Vaults secrets API, and subagents. |
| **OpenAI** — Agent Builder workflow, headlessly runnable by ID | **Agent Builder** (AgentKit) lets you build a workflow and **publish it as a persistent, OpenAI-hosted, versioned object** (`wf_...`). It IS callable headless: **`POST /v1/workflows/{id}/run`**, header `OpenAI-Beta: workflows=v1`. One gotcha that cost a day: you must set the workflow variable (`input_as_text`) in the body alongside `input`, and `stream: true` to recover usage/output (the non-streaming response leaves `result.output` null). Also reachable via **ChatKit** (chat-shaped) and exportable as **Agents SDK** code (self-host). The stateful **Assistants API** is **deprecated, sunset 2026-08-26**. |

So for OpenAI this repo benchmarks the **real hosted Agent Builder workflow** (`wf_68f0aace...`), not a Responses proxy. All three are now apples-to-apples managed run-by-ID loops.

## Headline result — managed vs a true local loop (N=6/cell, 108 runs, same tasks)

Fair test: the provider's managed runtime vs a loop on my own machine (model via API, **code executes locally for free**), same tasks, caching read as-used. OpenAI = the real hosted Agent Builder workflow via `/v1/workflows/{id}/run`.

| Provider (model) | Cost: managed vs local (avg) | What "managed" charges for | Latency |
|---|---|---|---|
| Anthropic (claude-haiku-4-5) | **~1.2× (about equal)** | almost nothing — caching absorbs the overhead | managed 2.8× slower |
| Google (gemini-3.5-flash) | **~5.3× more** | the always-on sandbox itself (still 2.9× on a no-code task) | managed 4.3× slower |
| OpenAI (gpt-5-mini) | **~1× on reasoning, +$0.03/code run** | the code container, per execution — not the runtime | ≈ local on reasoning; ~19s on the code task |

**The averages hide the real finding — read it per task** (managed/local cost ratio, + did the agent run code?):

| Task | runs code? | Google | Anthropic | OpenAI |
|---|---|---|---|---|
| T1 prime-sum | yes | 7.0× | 1.3× | **~65×** ($0.0306 vs $0.0005 — the container fee) |
| T2 mean-of-squares | mixed | 8.0× | 1.6× | **~1.0×** |
| T3 bat&ball (pure reasoning) | no | **2.9×** | 0.7× | **~0.6× (cheaper)** |

Three different bets: **Google charges for the runtime** (flat, even idle), **Anthropic charges ~nothing** (caching), **OpenAI charges per code-execution** (nothing otherwise). The model decides whether to run code, so OpenAI's managed cost is workload-dependent, not fixed.

Plus: a single agent **definition** (instructions + `SKILL.md` + files) ran on Google's managed cloud sandbox **and** on Claude locally and caught the same bug; one `AGENTS.md` format rule was obeyed 100% across Google Managed Agents, Gemini direct, and Claude. The portable thing is the definition; the runtime is a deploy choice.

**Caveats (important):** tasks were within model capability, so every cell hit 100% pass — this is a cost/latency/architecture finding, **not** a reliability-cliff result. Cost is a token-based estimate at published tier rates (plus OpenAI's `code_interpreter` container fee and Anthropic cache pricing). Managed runtimes auto-cache a large context; the local loop's context is lean (reported as-used). Full log + corrections in [`FINDINGS.md`](FINDINGS.md).

## Setup

```bash
pip install -r requirements.txt          # anthropic + openai SDKs; Gemini uses stdlib
cp .env.example .env                      # then add GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY
```

`GEMINI_API_KEY` needs Managed Agents preview access; `ANTHROPIC_API_KEY` needs the managed-agents beta. Scripts read `.env` from the repo root automatically.

## Run it

```bash
python scripts/clean_comparison.py --n 6           # THE headline: managed loop vs local loop, all 3 providers (OpenAI arm = real hosted Agent Builder workflow; set OAI_WORKFLOW_ID to your own wf_...)
python scripts/runner.py --tasks T1,T2,T3,T4 --arms A,B,C --n 25   # Google battery + portability task
python scripts/anthropic_managed_runner.py --n 12  # Anthropic managed vs single call
python scripts/openai_runner.py --n 12             # OpenAI Responses+code_interpreter vs single call
python scripts/translator.py                       # Gemini <-> Anthropic translator, live tests
python scripts/probe_advanced.py                   # Google Managed Agents: skills / MCP / secrets / subagents
```

Each script writes structured logs to `data/` and a report to `outputs/`. Full per-script guide: [`CLAUDE.md`](CLAUDE.md).

## Layout

```
scripts/          runners, provider clients, the translator
data/             raw per-run logs (.jsonl) + API responses (the receipts)
outputs/          human-readable reports — start with comparison-clean.md
anthropic-local/  a code-defined LOCAL Claude agent (CLAUDE.md + .claude/skills + files)
FINDINGS.md       durable running log of every test, result, and correction
```

## License

MIT — see [LICENSE](LICENSE).
