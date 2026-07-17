# Career Counseling Agent

A working reference implementation of an agentic conversational application built on Anthropic's Managed Agents API. The agent helps students in grades 10–12 explore academic streams and career paths through structured, empathetic dialogue.

## What this demonstrates

- **Persistent agent state** — agent and environment provisioned once, reused across many sessions
- **Cloud-hosted execution** — agent runs in an isolated cloud environment with networking enabled
- **Streaming session events** — responses stream token-by-token through the session events API
- **Clean separation of provisioning and runtime** — one-time setup is decoupled from interactive use, which matters once you're managing more than a handful of agents

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/career-counseling-agent.git
cd career-counseling-agent
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
python setup.py    # creates the agent + environment, writes IDs to .env
python chat.py     # opens an interactive chat session
```

You should see something like:

```
🎓 Career Advisor Session Started (sesn_...)
Type your message and press Enter. Ctrl+C to quit.

You: I like biology and helping people. Should I go for medicine or psychology?
Advisor: Both are excellent paths and they share some important qualities...
```

## Files

| File | Purpose |
|---|---|
| `setup.py` | One-time agent + environment provisioning |
| `chat.py` | Interactive chat loop (run for every conversation) |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template — your real `.env` is created automatically by `setup.py` |
| `.gitignore` | Excludes `.env` and the usual Python/IDE noise |

## Notes

- This uses the `managed-agents-2026-04-01` beta. Your API key needs access to that beta.
- Don't commit your `.env` file. The included `.gitignore` handles this — but double-check before pushing.
- Re-running `setup.py` will refuse to overwrite an existing `.env`. If you delete `.env` to recreate, you will orphan the previously created agent and environment.

## License

MIT — use it, fork it, ship it.
