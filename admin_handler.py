"""
Admin handler — manages admin mode commands for Lexy.
Handles message storage, retrieval, and analytics.
"""

import json
import logging
import os
from datetime import datetime
from config import ADMIN_PASSWORD, CONTACTS_FILE, MESSAGES_FILE, MEMORY_FILE

logger = logging.getLogger(__name__)


# ─── Number Utilities ───────────────────────────────────────────

def normalize_number(num):
    """Normalize a phone number by taking the last 9 digits."""
    return "".join(c for c in num if c.isdigit())[-9:]


def verify_admin_password(password):
    """Check if a password matches the admin password."""
    return password == ADMIN_PASSWORD


# ─── Contacts ───────────────────────────────────────────────────

def load_contacts():
    """Load contacts from contacts.json."""
    if not os.path.exists(CONTACTS_FILE):
        return {}
    try:
        with open(CONTACTS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_contacts(contacts):
    """Save contacts to contacts.json."""
    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f, indent=2)


def get_contact_name(number):
    """Look up a contact name by number. Returns None if not found."""
    contacts = load_contacts()
    # Try exact match
    if number in contacts:
        return contacts[number]
    # Try normalized match
    norm = normalize_number(number)
    for saved_num, name in contacts.items():
        if normalize_number(saved_num) == norm:
            return name
    return None


def save_contact_name(number, name):
    """Save a contact name mapping."""
    contacts = load_contacts()
    contacts[number] = name
    save_contacts(contacts)


# ─── Messages ───────────────────────────────────────────────────

def load_messages():
    """Load all intentional messages from messages.json."""
    if not os.path.exists(MESSAGES_FILE):
        return {"messages": []}
    try:
        with open(MESSAGES_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"messages": []}


def save_messages_data(data):
    """Save messages data to messages.json."""
    with open(MESSAGES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _next_id(messages):
    """Get the next message ID."""
    if not messages:
        return 1
    return max(m["id"] for m in messages) + 1


def save_intentional_message(sender_name, sender_number, content):
    """Save an intentional message left for the business owner."""
    data = load_messages()
    msg = {
        "id": _next_id(data["messages"]),
        "sender_name": sender_name,
        "sender_number": sender_number,
        "timestamp": datetime.now().isoformat(),
        "content": content,
        "status": "unread",
    }
    data["messages"].append(msg)
    save_messages_data(data)
    logger.info("Message saved from %s (%s)", sender_name, sender_number)
    return msg


def get_unread_count():
    """Get count of unread messages."""
    data = load_messages()
    return sum(1 for m in data["messages"] if m["status"] == "unread")


def get_messages_overview():
    """Get overview of all messages grouped by sender."""
    data = load_messages()
    senders = {}
    for m in data["messages"]:
        key = m["sender_name"]
        if key not in senders:
            senders[key] = {"name": m["sender_name"], "number": m["sender_number"], "total": 0, "unread": 0}
        senders[key]["total"] += 1
        if m["status"] == "unread":
            senders[key]["unread"] += 1
    return senders


def get_messages_from(sender_name):
    """Get all messages from a specific sender by name."""
    data = load_messages()
    name_lower = sender_name.lower()
    return [m for m in data["messages"] if m["sender_name"].lower() == name_lower]


def mark_all_read(sender_name=None):
    """Mark messages as read. If name given, only that sender's messages."""
    data = load_messages()
    name_lower = sender_name.lower() if sender_name else None
    for m in data["messages"]:
        if name_lower is None or m["sender_name"].lower() == name_lower:
            m["status"] = "read"
    save_messages_data(data)


# ─── Chat History Analysis ──────────────────────────────────────

def get_chat_history(sender_name):
    """Get chat history with a specific person from memory files."""
    name_lower = sender_name.lower()
    # Search all memory files for mentions of this name
    mem_dir = os.path.dirname(MEMORY_FILE) or "."
    prefix = os.path.splitext(os.path.basename(MEMORY_FILE))[0]
    chats = []

    for fname in os.listdir(mem_dir):
        if fname.startswith(prefix) and fname.endswith(".json"):
            fpath = os.path.join(mem_dir, fname)
            try:
                with open(fpath, "r") as f:
                    history = json.load(f)
                for entry in history:
                    content = entry.get("content", "").lower()
                    if name_lower in content:
                        chats.append(entry)
            except (json.JSONDecodeError, IOError):
                continue

    return chats


def get_topic_analysis():
    """Analyze chat history to find common topics."""
    mem_dir = os.path.dirname(MEMORY_FILE) or "."
    prefix = os.path.splitext(os.path.basename(MEMORY_FILE))[0]
    topics = {
        "weather": 0,
        "business": 0,
        "service": 0,
        "tech": 0,
        "general": 0,
    }

    keywords = {
        "weather": ["weather", "temperature", "rain", "sunny", "cloudy", "forecast"],
        "business": ["business", "shop", "market", "sell", "buy", "entrepreneur", "startup"],
        "service": ["service", "appointment", "booking", "schedule", "help", "support", "pricing"],
        "tech": ["tech", "ai", "digital", "app", "website", "software", "developer"],
    }

    for fname in os.listdir(mem_dir):
        if fname.startswith(prefix) and fname.endswith(".json"):
            fpath = os.path.join(mem_dir, fname)
            try:
                with open(fpath, "r") as f:
                    history = json.load(f)
                for entry in history:
                    content = entry.get("content", "").lower()
                    for topic, words in keywords.items():
                        if any(w in content for w in words):
                            topics[topic] += 1
            except (json.JSONDecodeError, IOError):
                continue

    return dict(sorted(topics.items(), key=lambda x: x[1], reverse=True))


def get_summary():
    """Generate a daily activity summary."""
    data = load_messages()
    total_messages = len(data["messages"])
    unique_people = len(set(m["sender_name"] for m in data["messages"]))
    unread = get_unread_count()
    topics = get_topic_analysis()

    return {
        "total_messages": total_messages,
        "unique_people": unique_people,
        "unread": unread,
        "top_topic": list(topics.keys())[0] if topics else "none",
    }
