# equity-research-agentic-workflow

A high-conviction tech equity research workflow for NASDAQ + NSE tech stocks (market cap >= $200M). Claude Code itself is the agentic layer — no LangGraph, no orchestration framework, no paid APIs. Run it manually on Thursday nights by asking Claude Code to "run weekly analysis"; the run produces 0-5 high-conviction picks (or none — empty inboxes are a feature) written to `runs/YYYY-MM-DD.md` with the full reasoning trace. See [MASTER_PLAN.md](MASTER_PLAN.md) for the strategy and [SKILL.md](SKILL.md) for the agent flow.

## How it runs

**Phase 1 — deterministic screener.** Runs every Thursday at 21:00 IST (15:30 UTC) via GitHub Actions — see [`.github/workflows/weekly-screen.yml`](.github/workflows/weekly-screen.yml). The workflow installs dependencies, runs the unit tests, executes `python -m tools.screen`, and commits the resulting `runs/screen_YYYY-MM-DD.csv` and `runs/screen_YYYY-MM-DD_rejected.csv` back to the same branch. With the Phase 1.6 universe expansion (~1,500 NASDAQ + NYSE + NSE tickers), expect a wall-clock runtime of **30–45 minutes** per run, dominated by yfinance fetches. Trigger on demand: **GitHub → Actions → weekly-screen → Run workflow**.

**Phase 2.5 — evidence collector tools.** [`tools/research.py`](tools/research.py) exposes eight functions the Analyst calls: `get_sec_filings`, `get_company_news`, `get_earnings_call_evidence`, `get_analyst_revisions`, `get_insider_activity`, `get_peer_reaction`, `get_governance_red_flags`, `get_macro_context`. Every return value carries a `sources[]` list with a `source_tier` field (A = SEC EDGAR / official PR, B = Reuters / AP / Finnhub aggregated). Tier C is dropped at ingest. CLI: `python -m tools.research <function> <ticker> [--sector S] [--days N]`.

**Phase 3 — three-question Analyst (the ReAct loop).** When you ask Claude Code to "run weekly analysis", it loads the latest screen CSV, takes the top 25 candidates, and answers three questions per ticker, capped at 12 tool calls each:

1. **Is this stock truly mispriced, or is the market right?** — peer reaction + news + recent 8-Ks classify the move as `mispricing_real`, `sector_wide`, `market_right`, or `insufficient_data`.
2. **If mispricing is real, is the cause TEMPORARY or STRUCTURAL?** — earnings transcript + analyst revisions classify the dislocation horizon. Only `temporary` or `medium` are PICK-eligible; `structural`/`permanent_impairment` is an automatic SKIP.
3. **What is the SINGLE biggest risk that could break this thesis?** — governance flags + insider activity surface the strongest counter-thesis with a concrete trigger that would change the call.

A rule-based Critic then issues PICK / WATCH / SKIP on the Q1 + Q2 + Q3 outputs and the original composite score. The full reasoning trace, citations included, lands in `runs/YYYY-MM-DD_react.md`. See [`CLAUDE.md`](CLAUDE.md) for the exact spec; an empty inbox is a feature, not a bug.
