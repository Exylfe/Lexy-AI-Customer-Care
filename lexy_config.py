"""
Lexy Configuration Manager — persists business info, personality,
working hours, and app settings to JSON. Follows the same pattern
as admin_handler.py (JSON files, load/save).
"""

import json
import logging
import os
from copy import deepcopy

from config import DATA_DIR

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(DATA_DIR, "lexy_settings.json")

# ─── Defaults ───────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "business": {
        "name": "",
        "type": "",
        "description": "",
        "website": "",
        "service_area": "",
        "language": "English",
    },
    "personality": {
        "tone": 0,            # -50 (friendly) to +50 (professional)
        "speed": "instant",   # "instant" | "natural" | "delayed"
        "use_emojis": True,
        "greeting_type": "auto",  # "auto" | "custom"
        "greeting_custom": "",
        "response_length": 0,  # -50 (brief) to +50 (detailed)
    },
    "hours": {
        "monday": {"open": True, "from": "09:00", "to": "17:00"},
        "tuesday": {"open": True, "from": "09:00", "to": "17:00"},
        "wednesday": {"open": True, "from": "09:00", "to": "17:00"},
        "thursday": {"open": True, "from": "09:00", "to": "17:00"},
        "friday": {"open": True, "from": "09:00", "to": "17:00"},
        "saturday": {"open": False, "from": "09:00", "to": "17:00"},
        "sunday": {"open": False, "from": "09:00", "to": "17:00"},
        "closed_message": "We're closed now. Open again at {next_time} tomorrow.",
        "holidays": [],
    },
    "app": {
        "auto_start": False,
        "minimize_tray": False,
        "show_tray_icon": True,
        "notifications": True,
        "sound_alerts": True,
        "show_preview": False,
        "debug_logs": False,
        "update_frequency": "automatic",
        "telemetry": False,
        "theme": "auto",       # "light" | "dark" | "auto"
        "font_size": "normal",  # "small" | "normal" | "large"
    },
    "whatsapp": {
        "connected": False,
        "number": "",
        "connected_since": "",
    },
    "channels": {
        "whatsapp": {"connected": False, "number": "", "connected_since": ""},
        "sms": {"connected": False, "config": {}},
        "telegram": {"connected": False, "config": {}},
        "email": {"connected": False, "config": {}},
        "facebook": {"connected": False, "config": {}},
    },
    "billing": {
        "plan": "free",
    },
    "setup_complete": False,
}


# ─── Load / Save ────────────────────────────────────────────────

def _load_raw():
    """Load raw JSON from disk."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load config: %s", e)
        return {}


def _save_raw(data):
    """Write JSON to disk atomically-ish."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_config():
    """Load saved config merged over defaults (so new keys appear)."""
    saved = _load_raw()
    config = deepcopy(DEFAULT_CONFIG)

    def deep_merge(base, overlay):
        for key, val in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(val, dict):
                deep_merge(base[key], val)
            else:
                base[key] = val

    deep_merge(config, saved)
    return config


def save_config(config):
    """Persist config to disk."""
    _save_raw(config)
    logger.info("Config saved")


def get_config():
    """Convenience: load and return."""
    return load_config()


# ─── Section Getters / Setters ─────────────────────────────────

def get_section(section):
    """Get a config section (business|personality|hours|app|whatsapp)."""
    return load_config().get(section, DEFAULT_CONFIG.get(section, {}))


def update_section(section, data):
    """Merge data into a config section and save."""
    config = load_config()
    if section not in config:
        config[section] = {}
    config[section].update(data)
    save_config(config)
    return config[section]


def reset_section(section):
    """Reset a section to defaults."""
    default = deepcopy(DEFAULT_CONFIG.get(section))
    if default is None:
        return False
    config = load_config()
    config[section] = default
    save_config(config)
    return True


# ─── Wizard / Setup ─────────────────────────────────────────────

def is_setup_complete():
    """Check if onboarding wizard has been completed."""
    return load_config().get("setup_complete", False)


def mark_setup_complete():
    """Mark onboarding as finished."""
    config = load_config()
    config["setup_complete"] = True
    save_config(config)


# ─── Hours helpers ──────────────────────────────────────────────

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def is_open_now():
    """Check if business is currently open based on configured hours."""
    from datetime import datetime
    config = load_config()
    now = datetime.now()
    day_name = now.strftime("%A").lower()
    if day_name not in DAY_NAMES:
        return False
    day = config.get("hours", {}).get(day_name, {})
    if not day.get("open", False):
        return False
    try:
        from_time = datetime.strptime(day["from"], "%H:%M").time()
        to_time = datetime.strptime(day["to"], "%H:%M").time()
        return from_time <= now.time() <= to_time
    except (ValueError, KeyError):
        return False


def get_closed_message():
    """Get the closed message template."""
    config = load_config()
    return config.get("hours", {}).get(
        "closed_message",
        "We're closed now. Open again at {next_time} tomorrow.",
    )


# ─── Personality helpers ────────────────────────────────────────

def get_tone_label(tone_value):
    """Map tone numeric to label."""
    if tone_value <= -30:
        return "friendly"
    elif tone_value >= 30:
        return "professional"
    return "balanced"


def get_speed_label(speed_value):
    """Map speed setting to human label."""
    labels = {"instant": "Instant", "natural": "Natural", "delayed": "Delayed"}
    return labels.get(speed_value, "Instant")
