import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from brain import chat
from config import BRAIN_SECRET

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp_server")

app = Flask(__name__)


def _authorized():
    """Check X-Brain-Secret header against configured secret."""
    if not BRAIN_SECRET:
        return True  # No secret configured = open (backward compat)
    return request.headers.get("X-Brain-Secret", "") == BRAIN_SECRET


@app.route("/chat", methods=["POST"])
def handle_chat():
    if not _authorized():
        logger.warning("Unauthorized request from %s", request.remote_addr)
        return jsonify({"reply": "Unauthorized"}), 401
    data = request.get_json(force=True)
    message = data.get("message", "")
    sender = data.get("sender")
    admin_mode = data.get("admin_mode", False)
    if not message:
        return jsonify({"reply": "(empty message received)"})
    logger.info("Chat from %s: %.50s (admin=%s)", sender or "anon", message, admin_mode)
    reply = chat(message, sender=sender, admin_mode=admin_mode)
    return jsonify({"reply": reply})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if BRAIN_SECRET:
        logger.info("Brain server running with auth on http://0.0.0.0:5005")
    else:
        logger.warning("No BRAIN_SECRET set — server is OPEN to the network!")
        logger.info("Brain server running on http://0.0.0.0:5005")
    app.run(host="0.0.0.0", port=5005)
