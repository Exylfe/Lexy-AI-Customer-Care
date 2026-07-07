"""
Run this for phone access via Telegram:
    python frontends/telegram_bot.py

Setup:
1. Message @BotFather on Telegram, send /newbot, follow prompts
2. Copy the token it gives you into config.py (TELEGRAM_BOT_TOKEN) or
   set it as an environment variable
3. Run this script, then message your bot on Telegram
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

from config import TELEGRAM_BOT_TOKEN
from brain import chat
from memory import clear_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    sender = str(update.message.from_user.id)

    # Show typing indicator while brain works
    async with context.application.create_task(
        update.message.chat.send_action("typing")
    ):
        pass
    reply = chat(user_text, sender=sender)
    await update.message.reply_text(reply)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm Jarvis, your personal assistant. "
        "Send me a message and I'll do my best to help.\n\n"
        "Commands:\n"
        "/clear — Reset your conversation memory"
    )


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = str(update.message.from_user.id)
    clear_history(sender)
    await update.message.reply_text("Memory cleared.")


def main():
    if "your-telegram-bot-token" in TELEGRAM_BOT_TOKEN or not TELEGRAM_BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN in .env or as an env var first.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Telegram bot running.")
    app.run_polling()


if __name__ == "__main__":
    main()
