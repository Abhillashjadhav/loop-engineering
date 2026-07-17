# Telegram Agentic Workflow

A personal AI assistant you control via **Telegram**. Send a message, and the agent executes real tasks — no paid APIs required.

## What It Can Do

| Command | Example |
|---------|---------|
| 📈 Stock prices | "What's Reliance stock price?" |
| 🔔 Price alerts | "Alert me when INFY crosses 1600" |
| 🔍 Web search | "Search for latest AI news" |
| 🍽️ Find restaurants | "Find Italian food near me" |
| 🛒 Place orders | "Order from Dominos" |

## Architecture

```
Telegram Message
      │
      ▼
  LangGraph Agent (agent.py)
      │
      ▼
  classify_intent ──► route to tool node
                           │
              ┌────────────┼────────────────┐
              ▼            ▼                ▼
       StockPriceTool  WebSearchTool   AlertsTool
       (yfinance)     (DuckDuckGo)     (SQLite)
              │            │                │
              └────────────┴────────────────┘
                           │
                      format_response
                           │
                           ▼
                    Telegram reply
```

**100% Free Stack:**
- LLM: [Ollama](https://ollama.ai) (llama2/mistral, runs locally)
- Messaging: Telegram Bot API (free forever)
- Stock data: yfinance (Yahoo Finance)
- Web search: BeautifulSoup + DuckDuckGo
- Database: SQLite (local file)

## Quick Start

### 1. Install Ollama (free local LLM)
```bash
# macOS
brew install ollama
ollama pull llama2

# Linux
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama2
```

### 2. Get a Telegram Bot Token
1. Open Telegram → search for **@BotFather**
2. Send `/newbot` and follow instructions
3. Copy your bot token

### 3. Set Up the Project
```bash
git clone https://github.com/abhillashjadhav/telegram-agentic-workflows.git
cd telegram-agentic-workflows

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your TELEGRAM_BOT_TOKEN
```

### 4. Test the Tools
```bash
python test_tools.py
```
All 5 tests should pass before running the bot.

### 5. Run the Bot
```bash
python bot.py
```

Open Telegram, find your bot, and start chatting!

## Project Structure

```
telegram-agentic-workflows/
├── agent.py              # LangGraph state machine (the brain)
├── bot.py                # Telegram bot integration
├── state.py              # AgentState definition
├── test_tools.py         # Test all tools independently
├── requirements.txt
├── .env.example
└── tools/
    ├── __init__.py
    ├── stock_prices.py   # yfinance stock data
    ├── web_scraper.py    # DuckDuckGo scraping
    ├── alerts.py         # SQLite price alerts
    └── restaurant_search.py  # Mock food delivery
```

## Example Conversation

```
You: What's Reliance stock price?
Bot: 📈 Reliance Industries (RELIANCE.NS)
     💰 Current: INR 2,847.50
     ▲ Change: INR +12.30 (+0.43%)

You: Alert me when INFY crosses 1600
Bot: ✅ Alert Created
     📊 INFY.NS ▲ 1,600.00
     I'll notify you when INFY.NS goes above ₹1,600.00

You: Search for latest AI agent news
Bot: 🔍 Search results for 'latest AI agent news':
     • OpenAI releases GPT-5...
     • Google DeepMind announces...
```

## Extending the Agent

To add a new tool:

1. Create `tools/my_tool.py` with your function
2. Export it in `tools/__init__.py`
3. Add a pattern to `INTENT_PATTERNS` in `agent.py`
4. Add a tool node function and wire it into the graph

## Built With

- [LangGraph](https://github.com/langchain-ai/langgraph) — agent orchestration
- [python-telegram-bot](https://python-telegram-bot.org/) — Telegram integration
- [yfinance](https://github.com/ranaroussi/yfinance) — stock data
- [Ollama](https://ollama.ai) — local LLM
