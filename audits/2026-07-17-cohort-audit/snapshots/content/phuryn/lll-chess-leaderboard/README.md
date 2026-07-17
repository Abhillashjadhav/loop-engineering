# The Silicon Gambit: High-Stakes LLM Chess Benchmark

A chess engine API designed for benchmarking LLM chess capabilities via n8n orchestration. Models play chess by outputting moves in Standard Algebraic Notation (SAN), and invalid moves result in automatic losses.

## Overview

- **Stateful HTTP JSON API** using [chess.js](https://github.com/jhlywa/chess.js)
- **Game persistence** with PostgreSQL (via Supabase)
- **Move validation** using Standard Algebraic Notation (SAN)
- **Game state detection**: checkmate, stalemate, draw, invalid moves
- **Player tracking** and leaderboard with points system
- **API Key protected** write endpoints

## Authentication

Write endpoints require an API key passed via the `x-api-key` header:

```
x-api-key: *****
```

**Protected endpoints:** `/new-game`, `/apply-move`, `/current-position`, `/legal-moves`

**Public access:** Database queries for stats and game details (no authentication required)

Requests without a valid API key will receive a `401 Unauthorized` response.

## API Documentation

Full API documentation is available in [APIdoc.md](./APIdoc.md) or at the [/docs](https://chess.productcompass.pm/docs) page.

### Quick Reference

| Endpoint | Description |
|----------|-------------|
| `POST /new-game` | Create a new game |
| `POST /current-position` | Get current game state |
| `POST /apply-move` | Apply a move to a game |
| `POST /legal-moves` | Get legal moves for a position |

**Status values:** `continue`, `mate`, `stalemate`, `draw`, `invalid_move`

## n8n Workflows

Pre-built n8n workflows are available in the `/n8n` folder:

| File | Description |
|------|-------------|
| `blind_mode.json` | Models reconstruct board state from move history only |
| `FEN_mode.json` | Models receive exact board position as FEN string |

### How to Import

1. Open your n8n instance
2. Go to **Workflows → Import from file**
3. Select the JSON file (`blind_mode.json` or `FEN_mode.json`)
4. Configure the HTTP Request nodes with your API endpoint URL
5. **Add `x-api-key` header** to all HTTP Request nodes (required for API authentication)
6. Add your **OpenRouter API keys** to the AI/LLM nodes
7. Activate the workflow

> **Note:** The provided workflows include a limited set of models. You may need to extend them to add more LLM models. The `x-api-key` header is **not included** in the workflow files and **must be manually added** to all HTTP Request node headers.

## Scoring System

- **Win**: +1 point
- **Loss**: -1 point
- **Draw**: +0.5 points
- **Invalid move**: Automatic loss (-1 point)

## Key Findings

### The Kimi-k2 and DeepSeek-V3.2 Reality Check

Kimi-k2 and DeepSeek-V3.2 lost often because they violated simple constraints: apologizing mid-game, inventing board states, or mixing reasoning with output.

Models that can't follow a basic negative rule ("don't add anything else") can't be trusted with write-access in production workflows.

### The Blindfold Paradox

Early games hinted that weaker models survived more moves when blindfolded (reconstructing the board from history) than when given the exact FEN snapshot. However, this pattern was not confirmed with additional testing—the effect was inconsistent across models and test runs.

**Why this could happen (in theory):** LLMs are trained on sequences, not compressed board snapshots. FEN requires spatial decompression, while PGN-like history aligns with autoregressive prediction. This remains an interesting hypothesis, but the data doesn't strongly support it.

### Catastrophic Forgetting

As games progress beyond 30+ moves, models in blind mode face **catastrophic forgetting**: they lose track of the board state as move history grows longer. Without explicit board snapshots, models must mentally reconstruct the entire game from scratch with each turn. As context expands, earlier moves fade from effective attention, leading to increasingly illegal moves.

### Scratchpad Mitigation

The n8n workflows provide blindfolded models with a **"Think" scratchpad tool** to maintain an internal board representation between turns. Models are prompted to use this scratchpad to keep track of the board state, simulating working memory that persists their mental board rather than reconstructing it from the full history each time.

## Technology Stack

- React + TypeScript + Vite
- Tailwind CSS + shadcn/ui
- Supabase (PostgreSQL + Edge Functions)
- chess.js for move validation

## Links

- **Live Leaderboard**: [View benchmark results](https://chess.productcompass.pm/)
- **Battle Statistics**: [/stats](https://chess.productcompass.pm/stats)
- **API Documentation**: [/docs](https://chess.productcompass.pm/docs)
- **Game Replays**: [/games](https://chess.productcompass.pm/games)
