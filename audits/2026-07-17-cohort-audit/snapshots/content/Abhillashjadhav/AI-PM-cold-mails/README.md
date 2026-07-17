# ai-pm-cold-emails
> The cold-email playbook for AI PMs targeting frontier labs.

## Why this exists
The AI PM job market in 2026 isn't won through applications. It's won through cold email + portfolio + a specific public hook. This repo is the unsentimental version of how that works — 12 dissected templates, the principles behind them, the failure modes that get auto-deleted, and the artifacts (Loom scripts, follow-up cadences, negotiation responses) that turn a reply into an offer.

Author background: 12-week build window targeting Anthropic, Cursor, Glean, Harvey, Decagon. Two shipped portfolio repos (rag-eval-harness, pm-evals). This repo documents the outreach layer that connects portfolio to offer.

## What's in here
- playbook/principles.md — 8 core principles distilled from analyzing 100+ public AI PM hires
- playbook/anatomy.md — the 5-paragraph structure that works (and why each paragraph exists)
- playbook/auto-reject-patterns.md — the 12 things that get cold emails deleted in 5 seconds
- playbook/timing-and-cadence.md — when to send, when to follow up, when to stop
- templates/ — 12 fully-written templates, one per target company tier
- artifacts/loom-scripts.md — 60-second Loom video scripts that pair with each email
- artifacts/follow-up-sequences.md — day-3, day-7, day-14 follow-ups that don't beg
- artifacts/reply-handling.md — what to say when they say yes, no, or maybe

## How to use
1. Read playbook/principles.md first — 10 minutes
2. Pick the closest template from templates/ based on the company tier (frontier lab / scale-up / Big Tech AI)
3. Customize the [HM name] and [specific public artifact] placeholders — these MUST be real, never generic
4. Record the Loom using artifacts/loom-scripts.md
5. Send. Follow artifacts/follow-up-sequences.md cadence.

## Expected response rates (honest)
- Frontier lab cold email with strong portfolio + specific hook: 25-40% reply rate
- Frontier lab cold email with weak hook or generic template: <5%
- Scale-up cold email with strong portfolio + specific hook: 35-55%
- Big Tech AI cold email: <10% regardless of quality (process-bound)

If you're below these numbers consistently, the problem is the portfolio, not the email.

## Author note
This repo is built on real outreach in the wild. It will be updated as response data comes in over the next 8 weeks. Star it if you want to see what works at scale.

## Companion repos
The templates here reference two portfolio repos as the artifacts you'd link in a cold email. They're the proof-of-work this playbook is built to point at:
- [pm-evals](https://github.com/Abhillashjadhav/pm-evals) — an LLM eval framework for PMs: English-authorable rubrics over 1,500 traces, with 3 case studies.
- [rag-eval-harness](https://github.com/Abhillashjadhav/rag-eval-harness) — eval-first single-turn RAG with LLM-as-judge, for measuring retrieval and answer quality.

## License
MIT. Steal everything.
