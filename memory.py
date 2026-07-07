import json
import logging
import os
from config import MEMORY_FILE, MAX_HISTORY_MESSAGES

logger = logging.getLogger(__name__)


def _get_memory_file(sender=None):
    """Get memory file path, optionally per-sender."""
    if sender:
        base, ext = os.path.splitext(MEMORY_FILE)
        return f"{base}_{sender}{ext}"
    return MEMORY_FILE


def load_history(sender=None):
    """Load past conversation history from disk. Returns a list of messages."""
    mem_file = _get_memory_file(sender)
    if not os.path.exists(mem_file):
        return []
    try:
        with open(mem_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_history(history, sender=None):
    """Save conversation history to disk, trimming to the max length."""
    mem_file = _get_memory_file(sender)
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    with open(mem_file, "w") as f:
        json.dump(trimmed, f, indent=2)


def append_message(history, role, content, tool_calls=None, tool_call_id=None, name=None, sender=None):
    """Add a message to history and persist it."""
    msg = {"role": role, "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if tool_call_id:
        msg["tool_call_id"] = tool_call_id
    if name:
        msg["name"] = name
    history.append(msg)
    save_history(history, sender)
    return history


def clear_history(sender=None):
    """Wipe saved memory. If sender is provided, only clears that sender's history."""
    if sender:
        mem_file = _get_memory_file(sender)
        if os.path.exists(mem_file):
            os.remove(mem_file)
    else:
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
