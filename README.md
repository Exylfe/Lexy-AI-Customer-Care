# my-jarvis

A small, hackable personal assistant. You chat with it, and it can call
tools (web search, weather, file read/write) to help answer you. The
"brain" is a free LLM API call (Groq) — nothing heavy runs on your machine.

## Setup

```bash
git init
pip install -r requirements.txt
```

Get a free Groq API key: https://console.groq.com (no card needed),
then either:
- set it as an environment variable: `export GROQ_API_KEY=your-key-here`
- or paste it directly into `config.py`

## Run it

**Terminal chat:**
```bash
python main.py
```

**Phone chat via Telegram:**
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. `export TELEGRAM_BOT_TOKEN=your-token-here`
3. `python frontends/telegram_bot.py`
4. Message your new bot from your phone

## Project layout

```
my-jarvis/
├── main.py              # terminal chat loop
├── brain.py             # core logic: talks to the LLM, handles tool calls
├── config.py            # API keys & settings
├── memory.py            # saves conversation history to memory.json
├── tools/
│   ├── web_search.py    # free DuckDuckGo search
│   ├── weather.py       # free Open-Meteo weather lookup
│   └── file_access.py   # sandboxed read/write to workspace/
└── frontends/
    └── telegram_bot.py  # phone access via Telegram
```

## Adding a new ability

1. Create `tools/your_tool.py` with two things:
   - `SCHEMA` — a dict describing the tool (name, description, parameters)
   - `run(**kwargs)` — the actual function
2. Register it in `tools/__init__.py` (add it to the `TOOLS` dict)

The LLM will automatically discover and use it when relevant — no other
wiring needed. Look at `tools/weather.py` as the simplest example to copy.

## Swapping the model/provider

Everything LLM-related lives in `config.py` and `brain.py`. To switch
providers (OpenAI, OpenRouter, local Ollama, etc.), just change `GROQ_URL`,
`GROQ_API_KEY`, and `MODEL` in `config.py` — as long as the new endpoint
speaks the OpenAI chat-completions format (most do), nothing else needs
to change.

## Notes

- Conversation memory is stored in `memory.json` — delete it (or type
  `clear` in the terminal) to reset.
- `file_access` is sandboxed to a `workspace/` folder so the assistant
  can never touch files outside it.
- This is intentionally small (~400 lines total) so you can read and
  understand every part of it.
