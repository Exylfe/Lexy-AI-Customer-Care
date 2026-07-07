import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Data directory — uses %APPDATA%/Lexy for persistent storage
# =============================================================================
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Lexy")
os.makedirs(DATA_DIR, exist_ok=True)

# =============================================================================
# LLM Provider chain — tried in order; falls back if one fails
# =============================================================================
PROVIDERS = [
    {
        "name": "groq",
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    {
        "name": "google",
        "api_key": os.environ.get(
            "GOOGLE_API_KEY",
            "your-google-api-key-here",
        ),
        "url": "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent",
        "model": "gemini-2.0-flash",
    },
]

# Telegram bot token (only needed if you use frontends/telegram_bot.py)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "your-telegram-bot-token-here")

# Admin password for admin mode (set via env var, fallback for setup)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# =============================================================================
# SYSTEM PROMPT — Lexy's base personality (customizable via dashboard)
# =============================================================================
SYSTEM_PROMPT = (
    "You are Lexy, a friendly and intelligent AI assistant. "
    "You help manage the business, answer customer questions, and handle tasks.\n\n"
    "Personality: You are clever, helpful, and genuinely friendly. "
    "You make jokes, use emojis, and have real personality — not robotic. "
    "You're confident and professional when needed.\n\n"
    "Your responsibilities:\n"
    "1. Help people with questions and tasks (use tools when helpful)\n"
    "2. Answer questions about the business accurately using the provided business info\n"
    "3. Be honest you're an AI while being genuinely helpful\n"
    "4. Keep conversations engaging and natural\n"
    "5. When asked to leave a message, collect the person's name and message, "
    "then say it'll be delivered\n\n"
    "You have access to web search, weather, and file tools. Prioritize accuracy and honesty. "
    "Have personality, be witty and sassy when appropriate, and genuinely care about helping people!"
)

# =============================================================================
# Admin command-mode prompt
# =============================================================================
COMMAND_PROMPT = (
    "You are Lexy, and the person you are talking to RIGHT NOW is the admin/owner.\n\n"
    "This is COMMAND MODE. The admin is not a regular user; they own you. Respond differently:\n"
    "- Be direct, concise, and efficient — no need for the full friendly greeting routine\n"
    "- Execute commands immediately and report results clearly\n"
    "- You can be more casual and technical — the admin knows what you can do\n"
    "- If the admin gives an instruction, confirm and carry it out\n"
    "- You can still be witty, but keep it efficient — the admin values speed\n\n"
    "Your core capabilities (web search, weather, file access) are all available. "
    "Just say what you're doing and deliver the results."
)

# =============================================================================
# Memory settings
# =============================================================================
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
MAX_HISTORY_MESSAGES = 20

# Optional shared secret for Flask ↔ WhatsApp bridge auth
BRAIN_SECRET = os.environ.get("BRAIN_SECRET", "")

# Data files
CONTACTS_FILE = os.path.join(DATA_DIR, "contacts.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
