"""
Lexy — AI assistant launcher.

Usage:
    python main.py                  Terminal chat
    python main.py --web            Web dashboard (port 5050)
    python main.py --dashboard      Same as --web
    python main.py --all            Terminal + dashboard
    python main.py --web --port 8080  Custom port
"""

import argparse
import logging
import sys

from brain import chat
from memory import clear_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

WEB_DEFAULT_PORT = 5050


def run_terminal():
    """Interactive terminal chat loop."""
    print("Lexy is ready. Type 'quit' to exit, 'clear' to wipe memory.\n")
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break
        if user_input.lower() == "clear":
            clear_history()
            print("Memory cleared.\n")
            continue

        reply = chat(user_input, sender=None)
        print(f"Lexy: {reply}\n")


def run_dashboard(port=WEB_DEFAULT_PORT):
    """Start the web dashboard."""
    from frontends.web_dashboard import app
    logger.info("Web dashboard starting on http://127.0.0.1:%d", port)
    app.run(host="127.0.0.1", port=port, debug=True)


def main():
    parser = argparse.ArgumentParser(description="Lexy AI Assistant")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--web", "--dashboard", action="store_true",
                      help="Start web dashboard instead of terminal")
    mode.add_argument("--all", action="store_true",
                      help="Start terminal + web dashboard together")
    parser.add_argument("--port", type=int, default=WEB_DEFAULT_PORT,
                        help=f"Web dashboard port (default: {WEB_DEFAULT_PORT})")
    args = parser.parse_args()

    if args.web:
        run_dashboard(args.port)
    elif args.all:
        import threading
        t = threading.Thread(target=run_dashboard, args=(args.port,), daemon=True)
        t.start()
        run_terminal()
    else:
        run_terminal()


if __name__ == "__main__":
    main()
