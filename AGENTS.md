# Lexy — Agent Work Guide

## Overview
An AI personal assistant built in Python that chats via terminal, Telegram, WhatsApp, and a web dashboard. Uses Groq's free LLM API (llama-3.3-70b-versatile) as its brain, with Google Gemini as fallback. Features admin mode, contact detection, message storage, tool calling (weather, web search, file access), and a config management system with a web-based setup wizard.

## Project Structure
```
Lexy/
├── main.py                    # CLI launcher — terminal chat, web dashboard, or both
├── brain.py                   # Core logic: talks to LLM via httpx, handles tool calls
├── config.py                  # API keys & settings (loads from .env via python-dotenv)
├── memory.py                  # Saves conversation history to memory_{sender}.json
├── lexy_config.py             # Config manager: business, personality, hours, app, WhatsApp
├── lexy_settings.json         # Persisted config (auto-created)
├── admin_handler.py           # Admin mode with password gate, admin commands
├── qr_watcher.py              # QR code watcher for WhatsApp bridge
├── .env                       # API keys (GROQ_API_KEY, TELEGRAM_BOT_TOKEN) — NOT committed
├── .gitignore                 # Excludes .env, auth_info/, memory*.json, __pycache__/
├── start.bat                  # Windows batch launcher (menu-driven)
├── start.ps1                  # PowerShell launcher (parameterized)
├── tools/
│   ├── __init__.py            # Auto-discovers tools from the directory (no manual registration)
│   ├── web_search.py          # DuckDuckGo API + Google HTML fallback
│   ├── weather.py             # Open-Meteo (free, no API key) with forecast support
│   └── file_access.py         # Sandboxed read/write to workspace/ folder
├── frontends/
│   ├── telegram_bot.py        # Phone chat via Telegram (with /start, /clear, typing indicator)
│   ├── whatsapp_server.py     # Flask API for WhatsApp bridge (port 5005)
│   ├── web_dashboard.py       # Flask web dashboard + setup wizard (port 5050)
│   ├── templates/
│   │   ├── wizard.html        # 5-step onboarding wizard
│   │   └── dashboard.html     # Full customization dashboard
│   ├── static/                # Static assets (empty, ready for future use)
│   └── __init__.py
├── whatsapp-bridge/
│   ├── index.js               # Node.js bridge using @whiskeysockets/baileys
│   └── package.json
├── contacts.json              # Saved contact names
├── messages.json              # Stored messages
├── requirements.txt
├── AGENTS.md
└── README.md
```

## Essential Commands

### Setup
```bash
pip install -r requirements.txt
```

### Running

**Terminal chat:**
```bash
python main.py
```
Commands: type anything to chat, `quit`/`exit` to stop, `clear` to wipe memory.

**Web Dashboard (setup wizard + settings):**
```bash
python main.py --web
# or: python frontends/web_dashboard.py
# Opens at http://127.0.0.1:5050
```

**Terminal + Dashboard together:**
```bash
python main.py --all
```

**Telegram:**
```bash
python frontends/telegram_bot.py
```

**WhatsApp (two terminals):**
```bash
# Terminal 1 — brain server
python frontends/whatsapp_server.py

# Terminal 2 — WhatsApp bridge
cd whatsapp-bridge && node index.js
```

### Quick Launchers
- `start.bat` — Windows batch menu (1-5)
- `start.ps1 -Mode web` — PowerShell launcher (modes: terminal/web/all/whatsapp/full)

## Architecture & Patterns

### brain.py — AI Engine
- Uses `httpx.Client` (replaces `requests`) with 60s timeout
- Retries on timeout up to 5 times
- Logs tool calls, errors, and API failures via Python `logging`
- Returns user-friendly error messages (no internal paths leaked)
- Supports per-sender memory via `sender` parameter

### config.py — Configuration
- `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `BRAIN_SECRET` loaded from `.env` or env vars
- Model: `llama-3.3-70b-versatile` on Groq
- Memory: `memory.json` (default) or `memory_{sender}.json` for per-user isolation
- Max 20 messages in context window

### memory.py — Persistence
- Saves/loads JSON conversation history
- Trims to `MAX_HISTORY_MESSAGES` to prevent context overflow
- Per-sender files via `memory_{sender}.json`

### Tool System — Auto-Discovery
Tools in `tools/` are **automatically discovered** — no manual registration needed. Each tool module needs:
1. `SCHEMA` dict — OpenAI-style function schema (name, description, parameters)
2. `run(**kwargs)` — implementation function

`tools/__init__.py` uses `pkgutil.iter_modules` to scan and import all tool modules at startup. Any module with `SCHEMA + run()` is registered.

### Available Tools

| Tool | API | Free? | Features |
|------|-----|-------|----------|
| **weather** | Open-Meteo | Yes | Current weather + 7-day forecast, geocode caching |
| **web_search** | DuckDuckGo → Google fallback | Yes | DDG instant answers, falls back to scraping Google HTML |
| **file_access** | Local filesystem | — | Sandboxed to workspace/, prevents path traversal |

### Frontend System

| Frontend | Tech | Port | Key Features |
|----------|------|------|--------------|
| Terminal | `main.py` (sync) | — | Simple loop, clear command |
| Telegram | `python-telegram-bot` (async) | — | `/start`, `/clear`, typing indicator, per-user memory |
| WhatsApp | Flask API + Node.js bridge | 5005 | Optional `X-Brain-Secret` auth, per-user memory |
| Web Dashboard | Flask + Jinja2 | 5050 | Setup wizard, business config, personality, working hours, app settings |

## Security Changes (applied June 2026)

- **API keys moved to `.env`** — no more hardcoded keys in `config.py`
- **`.gitignore`** — excludes `.env`, `auth_info/`, `memory*.json`, `__pycache__/`
- **`auth_info/` removed from git** — 1000+ WhatsApp credential files no longer tracked
- **Flask auth** — optional `BRAIN_SECRET` env var; bridge sends `X-Brain-Secret` header
- **Sandbox hardening** — `file_access.py` uses `os.path.normpath` to prevent path traversal

## Important Gotchas

- **Memory files are plain JSON** — deleting `memory*.json` resets the bot. Format errors break loading.
- **WhatsApp auth is fragile** — `auth_info/` contains session keys. If it gets out of sync, delete it and re-scan the QR code.
- **Google HTML fallback is slow** — web search falls back to scraping Google (no API key). Takes 3-5s. Add a Tavily/SerpAPI key later for speed.
- **No tests** — improvements are done manually. Add pytest if reliability matters.
- **Tool auto-discovery** — new tool files in `tools/` are picked up automatically, but the module must not error on import.

## Adding a New Tool
```python
# tools/my_tool.py
SCHEMA = {
    "name": "my_tool",
    "description": "What it does",
    "parameters": {
        "type": "object",
        "properties": {"param": {"type": "string"}},
        "required": ["param"],
    },
}

def run(param):
    return f"Got: {param}"
```
That's it — `tools/__init__.py` discovers it automatically.
