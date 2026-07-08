"""
Lexy Web Dashboard — serves the setup wizard and customization panel.
Run: python frontends/web_dashboard.py
"""

import sys
import os
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
from lexy_config import (
    load_config, save_config, get_section, update_section,
    reset_section, is_setup_complete, mark_setup_complete,
    DEFAULT_CONFIG,
)
from supabase_client import get_service_client, get_anon_client, get_profile as supabase_get_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("web_dashboard")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "lexy-dashboard-secret-change-me")

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


# ─── Validation helpers ─────────────────────────────────────────

ALLOWED_SECTIONS = ("business", "personality", "hours", "app", "whatsapp", "channels")

TIME_SLOTS = [f"{h:02d}:00" for h in range(6, 24)]


def _validate_section(section):
    if section not in ALLOWED_SECTIONS:
        return jsonify({"error": "unknown section"}), 400
    return None


def _validate_time(from_time, to_time):
    """Check from < to and both are valid HH:MM times."""
    try:
        from_parts = from_time.split(":")
        to_parts = to_time.split(":")
        if len(from_parts) != 2 or len(to_parts) != 2:
            return False
        from_mins = int(from_parts[0]) * 60 + int(from_parts[1])
        to_mins = int(to_parts[0]) * 60 + int(to_parts[1])
        return from_mins < to_mins
    except (ValueError, IndexError):
        return False


def _validate_hours_data(data):
    """Validate a hours payload: day times, open/closed types."""
    for day_data in data.values():
        if not isinstance(day_data, dict):
            return "invalid day data"
        if "open" in day_data and not isinstance(day_data["open"], bool):
            return "open must be boolean"
        if day_data.get("open") and day_data.get("from") and day_data.get("to"):
            if not _validate_time(day_data["from"], day_data["to"]):
                return f"from must be before to ({day_data['from']} → {day_data['to']})"
    return None


# ─── Pages ──────────────────────────────────────────────────────

@app.route("/")
def index():
    """Landing page — redirect to wizard or dashboard."""
    if is_setup_complete():
        return redirect(url_for("dashboard"))
    return redirect(url_for("wizard"))


@app.route("/wizard")
def wizard():
    """Setup wizard (5-step onboarding)."""
    config = load_config()
    return render_template("wizard.html", config=config)


@app.route("/dashboard")
def dashboard():
    """Main customization dashboard."""
    config = load_config()
    return render_template("dashboard.html", config=config)


# ─── Supabase Auth ───────────────────────────────────────────────


@app.route("/api/auth/signup", methods=["POST"])
def api_auth_signup():
    """Create a new Supabase account. Returns session + profile."""
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    client = get_service_client()
    if not client:
        return jsonify({"error": "Supabase not configured"}), 501

    try:
        resp = client.auth.sign_up({"email": email, "password": password})
        user = resp.user
        if not user:
            return jsonify({"error": "Signup failed — no user returned"}), 500

        # Profile is auto-created by the handle_new_user() trigger
        session["supabase_user_id"] = user.id
        session["supabase_email"] = email
        logger.info("User signed up: %s (%s)", email, user.id)

        return jsonify({
            "status": "ok",
            "user": {"id": user.id, "email": email},
        })
    except Exception as e:
        err_msg = str(e)
        # Supabase returns user-friendly error messages
        if "already registered" in err_msg.lower():
            return jsonify({"error": "This email is already registered. Try logging in."}), 409
        logger.warning("Signup failed: %s", err_msg)
        return jsonify({"error": err_msg}), 400


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    """Log in with email/password. Stores user_id in session."""
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    client = get_service_client()
    if not client:
        return jsonify({"error": "Supabase not configured"}), 501

    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        user = resp.user
        if not user:
            return jsonify({"error": "Login failed"}), 401

        session["supabase_user_id"] = user.id
        session["supabase_email"] = email
        logger.info("User logged in: %s", email)

        # Fetch profile
        profile = supabase_get_profile(user.id) or {}

        return jsonify({
            "status": "ok",
            "user": {
                "id": user.id,
                "email": email,
                "business_name": profile.get("business_name", ""),
                "current_tier": profile.get("current_tier", "Free"),
                "messages_used": profile.get("messages_used", 0),
                "message_limit": profile.get("message_limit", 1500),
            },
        })
    except Exception as e:
        err_msg = str(e)
        if "invalid login" in err_msg.lower() or "invalid credentials" in err_msg.lower():
            return jsonify({"error": "Invalid email or password"}), 401
        logger.warning("Login failed: %s", err_msg)
        return jsonify({"error": err_msg}), 400


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    """Log out and clear session."""
    client = get_service_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    session.pop("supabase_user_id", None)
    session.pop("supabase_email", None)
    return jsonify({"status": "ok"})


@app.route("/api/auth/status", methods=["GET"])
def api_auth_status():
    """Return current auth status."""
    user_id = session.get("supabase_user_id")
    if not user_id:
        return jsonify({"authenticated": False})

    profile = supabase_get_profile(user_id) if user_id else None
    return jsonify({
        "authenticated": True,
        "user": {
            "id": user_id,
            "email": session.get("supabase_email", ""),
            "business_name": profile.get("business_name", "") if profile else "",
            "current_tier": profile.get("current_tier", "Free") if profile else "Free",
            "messages_used": profile.get("messages_used", 0) if profile else 0,
            "message_limit": profile.get("message_limit", 1500) if profile else 1500,
        },
    })


# ─── API: Config CRUD ──────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_get_config():
    """Return full config as JSON."""
    return jsonify(load_config())


@app.route("/api/config/<section>", methods=["GET"])
def api_get_section(section):
    """Get a single config section."""
    err = _validate_section(section)
    if err:
        return err
    return jsonify(get_section(section))


@app.route("/api/config/<section>", methods=["PATCH"])
def api_patch_section(section):
    """Update fields within a config section."""
    err = _validate_section(section)
    if err:
        return err
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    if section == "hours":
        reason = _validate_hours_data(data)
        if reason:
            return jsonify({"error": reason}), 400
    if section == "app" and "theme" in data:
        if data["theme"] not in ("light", "dark", "auto"):
            return jsonify({"error": "theme must be light, dark, or auto"}), 400
        if "font_size" in data and data["font_size"] not in ("small", "normal", "large"):
            return jsonify({"error": "font_size must be small, normal, or large"}), 400
    updated = update_section(section, data)
    return jsonify({"status": "ok", "section": updated})


@app.route("/api/config/<section>/reset", methods=["POST"])
def api_reset_section(section):
    """Reset a section to default values."""
    err = _validate_section(section)
    if err:
        return err
    if reset_section(section):
        return jsonify({"status": "ok", "section": DEFAULT_CONFIG.get(section, {})})
    return jsonify({"error": "reset failed"}), 500


# ─── API: Wizard ────────────────────────────────────────────────

@app.route("/api/wizard/step/<int:step>", methods=["POST"])
def api_wizard_step(step):
    """Save wizard step data. step is 1-4 (step 0 and 5 have no data)."""
    if step < 1 or step > 4:
        return jsonify({"error": "invalid step"}), 400
    data = request.get_json(force=True)
    section_map = {1: "business", 2: "whatsapp", 3: "personality", 4: "none"}
    if section_map[step] != "none":
        update_section(section_map[step], data)
    if step == 4:
        mark_setup_complete()
    return jsonify({"status": "ok", "next_step": step + 1})


@app.route("/api/wizard/complete", methods=["POST"])
def api_wizard_complete():
    """Manually mark wizard complete."""
    mark_setup_complete()
    return jsonify({"status": "ok", "redirect": url_for("dashboard")})


# ─── API: Working Hours Helpers ────────────────────────────────

@app.route("/api/hours/copy-weekdays", methods=["POST"])
def api_copy_weekdays():
    """Copy Monday-Friday schedule to Saturday and Sunday."""
    config = load_config()
    hours = config.get("hours", {})
    if hours.get("monday"):
        template = {
            "from": hours["monday"]["from"],
            "to": hours["monday"]["to"],
        }
        for day in ["saturday", "sunday"]:
            if day in hours:
                hours[day]["from"] = template["from"]
                hours[day]["to"] = template["to"]
    save_config(config)
    return jsonify({"status": "ok", "hours": hours})


@app.route("/api/hours/close-all", methods=["POST"])
def api_close_all():
    """Set all days to closed."""
    config = load_config()
    hours = config.get("hours", {})
    for day_name in ["monday", "tuesday", "wednesday", "thursday",
                      "friday", "saturday", "sunday"]:
        if day_name in hours:
            hours[day_name]["open"] = False
    save_config(config)
    return jsonify({"status": "ok", "hours": hours})


@app.route("/api/holiday", methods=["POST"])
def api_add_holiday():
    """Add a special holiday."""
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    date_str = data.get("date", "").strip()
    if not date_str:
        return jsonify({"error": "date required"}), 400
    # Validate YYYY-MM-DD format
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD format"}), 400
    config = load_config()
    holidays = config["hours"].setdefault("holidays", [])
    # Avoid duplicates
    for existing in holidays:
        if existing.get("date") == date_str:
            return jsonify({"error": "holiday already exists for this date"}), 409
    holidays.append({
        "date": date_str,
        "label": data.get("label", "").strip(),
        "closed": data.get("closed", True),
        "from": data.get("from", ""),
        "to": data.get("to", ""),
    })
    save_config(config)
    return jsonify({"status": "ok", "holidays": holidays})


@app.route("/api/holiday/<int:index>", methods=["DELETE"])
def api_remove_holiday(index):
    """Remove a holiday by index."""
    config = load_config()
    holidays = config["hours"].setdefault("holidays", [])
    if 0 <= index < len(holidays):
        holidays.pop(index)
        save_config(config)
        return jsonify({"status": "ok", "holidays": holidays})
    return jsonify({"error": "index out of range"}), 400


# ─── API: QR Code ────────────────────────────────────────────────

QR_PNG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "whatsapp-bridge", "qr.png")
QR_TXT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "whatsapp-bridge", "qr.txt")


@app.route("/api/qr")
def api_qr_image():
    """Serve the WhatsApp QR code PNG if available."""
    if os.path.exists(QR_PNG):
        return send_file(QR_PNG, mimetype="image/png")
    return jsonify({"error": "no qr yet"}), 404


@app.route("/api/qr-status")
def api_qr_status():
    """Check if a QR code is available."""
    return jsonify({
        "available": os.path.exists(QR_PNG),
        "bridge_running": os.path.exists(QR_TXT),
    })


# ─── API: Channel Management ─────────────────────────────────────


@app.route("/api/channels", methods=["GET"])
def api_get_channels():
    """Get all connected channel statuses."""
    config = load_config()
    return jsonify(config.get("channels", {}))


@app.route("/api/channels/<channel>/connect", methods=["POST"])
def api_connect_channel(channel):
    """Connect a channel by saving its config."""
    allowed = ("whatsapp", "sms", "telegram", "email", "facebook")
    if channel not in allowed:
        return jsonify({"error": f"unknown channel '{channel}'"}), 400

    data = request.get_json(force=True) or {}

    config = load_config()
    if "channels" not in config:
        config["channels"] = {}
    if channel not in config["channels"]:
        config["channels"][channel] = {"connected": False, "config": {}}

    config["channels"][channel].update({
        "connected": True,
        "connected_since": data.get("connected_since", ""),
        "config": data.get("config", config["channels"][channel].get("config", {})),
    })
    if "number" in data:
        config["channels"][channel]["number"] = data["number"]

    save_config(config)
    logger.info("Channel '%s' connected", channel)
    return jsonify({"status": "ok", "channel": config["channels"][channel]})


@app.route("/api/channels/<channel>/disconnect", methods=["POST"])
def api_disconnect_channel(channel):
    """Disconnect a channel."""
    allowed = ("whatsapp", "sms", "telegram", "email", "facebook")
    if channel not in allowed:
        return jsonify({"error": f"unknown channel '{channel}'"}), 400

    config = load_config()
    if channel in config.get("channels", {}):
        config["channels"][channel] = {"connected": False, "config": {}}

    save_config(config)
    logger.info("Channel '%s' disconnected", channel)
    return jsonify({"status": "ok", "channel": config["channels"][channel]})


# ─── API: Knowledge Base ─────────────────────────────────────────

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB global cap (enforced by Flask too)
ALLOWED_KB_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


@app.route("/api/knowledge", methods=["GET"])
def api_kb_list():
    """List all uploaded documents."""
    from knowledge_base import list_documents, get_quota
    return jsonify({"documents": list_documents(), "quota": get_quota()})


@app.route("/api/knowledge/upload", methods=["POST"])
def api_kb_upload():
    """Upload documents (multipart). Syncs to Supabase for RAG if authenticated."""
    from knowledge_base import upload_documents, get_quota, sync_document_to_supabase

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    # 1. Enforce document count limit server-side (dev brief §3)
    user_id = session.get("supabase_user_id")
    if user_id:
        from supabase_client import get_document_count
        profile = supabase_get_profile(user_id)
        tier = (profile or {}).get("current_tier", "Free")
        tier_doc_limits = {"Free": 3, "Starter": 3, "Business": 999, "Enterprise": 9999}
        doc_limit = tier_doc_limits.get(tier, 3)
        current_count = get_document_count(user_id) or 0
        if current_count >= doc_limit:
            return jsonify({
                "error": f"Document limit reached for {tier} tier ({doc_limit} documents). Upgrade to add more.",
                "results": [],
                "quota": get_quota(),
            }), 403

    # 2. Save locally first
    results = upload_documents(files)

    # 3. For successful uploads, sync to Supabase with chunking + embeddings
    if user_id:
        from knowledge_base import get_document
        for r in results:
            if r["status"] == "ok":
                doc = get_document(r["id"])
                if doc and doc.get("content"):
                    sync_document_to_supabase(
                        profile_id=user_id,
                        doc_name=doc["name"],
                        text_content=doc["content"],
                    )

    errors = [r for r in results if r["status"] == "error"]
    status_code = 207 if errors else 200

    return jsonify({"results": results, "quota": get_quota()}), status_code


@app.route("/api/knowledge/<doc_id>", methods=["GET"])
def api_kb_get(doc_id):
    """Get document details with extracted text."""
    from knowledge_base import get_document
    doc = get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(doc)


@app.route("/api/knowledge/<doc_id>", methods=["DELETE"])
def api_kb_delete(doc_id):
    """Delete a document."""
    from knowledge_base import delete_document, get_document, get_quota, delete_profile_documents_local

    # Get doc info before deleting (for Supabase cleanup)
    doc = get_document(doc_id)
    user_id = session.get("supabase_user_id")

    if delete_document(doc_id):
        # Clean up Supabase chunks for this doc
        if user_id and doc:
            delete_profile_documents_local(user_id, doc_name=doc.get("name", ""))
        return jsonify({"status": "ok", "quota": get_quota()})
    return jsonify({"error": "Document not found"}), 404


@app.route("/api/knowledge/quota", methods=["GET"])
def api_kb_quota():
    """Get storage usage and limits."""
    from knowledge_base import get_quota
    return jsonify(get_quota())


# ─── API: Billing & Plan ────────────────────────────────────────


@app.route("/api/billing", methods=["GET"])
def api_billing():
    """Get current billing/plan info, preferring Supabase profile data."""
    from knowledge_base import get_quota
    config = load_config()
    billing = config.get("billing", {"plan": "free"})
    quota = get_quota()

    # Try to get real usage from Supabase if user is authenticated
    user_id = session.get("supabase_user_id")
    messages_used = 0
    message_limit = 1500
    if user_id:
        profile = supabase_get_profile(user_id)
        if profile:
            messages_used = profile.get("messages_used", 0)
            message_limit = profile.get("message_limit", 1500)
            # Sync plan from Supabase profile
            supabase_tier = profile.get("current_tier", "").lower()
            if supabase_tier in ("free", "starter", "business", "enterprise"):
                billing["plan"] = "free" if supabase_tier == "free" else \
                                  "starter" if supabase_tier == "starter" else "pro"
    else:
        # Fallback to local config values
        messages_used = billing.get("messages_used", 234)
        message_limit = billing.get("messages_limit", 1500 if billing["plan"] == "free" else (50000 if billing["plan"] == "starter" else 999999))

    plan_limits = {"free": 1500, "starter": 50000, "pro": 999999}
    return jsonify({
        "plan": billing["plan"],
        "quota": quota,
        "messages_used": messages_used,
        "messages_limit": message_limit,
    })


@app.route("/api/billing/plan", methods=["PATCH"])
def api_update_plan():
    """Upgrade or downgrade the billing plan."""
    data = request.get_json(force=True)
    plan = data.get("plan", "").strip().lower()
    if plan not in ("free", "starter", "pro"):
        return jsonify({"error": "plan must be 'free', 'starter', or 'pro'"}), 400

    config = load_config()
    config.setdefault("billing", {})["plan"] = plan
    save_config(config)
    logger.info("Plan upgraded to '%s'", plan)

    # Also sync to Supabase profile if authenticated
    user_id = session.get("supabase_user_id")
    if user_id:
        tier_map = {"free": "Free", "starter": "Starter", "pro": "Business"}
        limit_map = {"free": 1500, "starter": 50000, "pro": 999999}
        client = get_service_client()
        if client:
            try:
                client.table("profiles").update({
                    "current_tier": tier_map.get(plan, "Free"),
                    "message_limit": limit_map.get(plan, 1500),
                }).eq("id", user_id).execute()
                logger.info("Synced plan change to Supabase for %s", user_id)
            except Exception as e:
                logger.warning("Failed to sync plan to Supabase: %s", e)

    from knowledge_base import get_quota
    return jsonify({"status": "ok", "plan": plan, "quota": get_quota()})


# ─── API: Status ────────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
def api_status():
    """Return overall system status."""
    from lexy_config import is_open_now
    config = load_config()
    return jsonify({
        "whatsapp_connected": config.get("whatsapp", {}).get("connected", False),
        "whatsapp_number": config.get("whatsapp", {}).get("number", ""),
        "setup_complete": config.get("setup_complete", False),
        "business_name": config.get("business", {}).get("name", ""),
        "is_open": is_open_now(),
        "theme": config.get("app", {}).get("theme", "auto"),
    })


# ─── API: Utility actions ──────────────────────────────────────

@app.route("/api/config/api-keys", methods=["GET"])
def api_get_api_keys():
    """Get current API key status (masked)."""
    config = load_config()
    apikeys = config.get("api_keys", {})
    return jsonify({
        "groq": _mask_key(apikeys.get("groq", "")),
        "google": _mask_key(apikeys.get("google", "")),
        "telegram": _mask_key(apikeys.get("telegram", "")),
        "has_groq": bool(apikeys.get("groq")),
        "has_google": bool(apikeys.get("google")),
    })


@app.route("/api/config/api-keys", methods=["PATCH"])
def api_save_api_keys():
    """Save API keys (stores in config, not .env)."""
    data = request.get_json(force=True)
    config = load_config()
    apikeys = config.setdefault("api_keys", {})

    allowed = ("groq", "google", "telegram")
    for key in allowed:
        if key in data and data[key]:
            apikeys[key] = data[key].strip()

    save_config(config)
    logger.info("API keys updated")
    return jsonify({"status": "ok"})


def _mask_key(key):
    """Show only first 8 chars of an API key."""
    if not key or len(key) < 12:
        return ""
    return key[:8] + "..." + key[-4:]

@app.route("/api/rescan-qr", methods=["POST"])
def api_rescan_qr():
    """Signal the WhatsApp bridge to regenerate QR."""
    import subprocess
    import platform
    try:
        # Touch the qr_watcher trigger or restart the bridge
        qr_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qr_watcher.py")
        if os.path.exists(qr_file):
            subprocess.Popen([sys.executable, qr_file])
        return jsonify({"status": "ok", "message": "QR refresh triggered"})
    except Exception as e:
        logger.warning("QR rescan failed: %s", e)
        return jsonify({"error": "bridge not reachable"}), 502


@app.route("/api/config/reset-all", methods=["POST"])
def api_reset_all():
    """Reset entire config to defaults and clear memory/messages."""
    from lexy_config import DEFAULT_CONFIG
    from config import DATA_DIR
    import shutil
    # Reset config
    save_config(DEFAULT_CONFIG)
    # Wipe JSON data files in APPDATA
    for fname in ("memory.json", "messages.json", "contacts.json"):
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, "w") as f:
                json.dump([], f) if fname == "memory.json" else json.dump({}, f)
    logger.info("All data reset to defaults")
    return jsonify({"status": "ok"})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """Return recent log lines for debugging."""
    log_file = None
    for candidate in ("lexy.log", "crash.log", os.path.expanduser("~/.lexy/lexy.log")):
        if os.path.exists(candidate):
            log_file = candidate
            break
    if not log_file:
        return jsonify({"logs": ["No log file found. Enable debug logs in App Settings."]})
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()[-200:]  # last 200 lines
        return jsonify({"logs": lines})
    except (IOError, OSError) as e:
        return jsonify({"error": f"cannot read logs: {e}"}), 500


# ─── Main ───────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    """Catch-all for unknown routes."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return render_template("dashboard.html", config=load_config()), 404


@app.errorhandler(500)
def server_error(e):
    """Internal server error."""
    logger.exception("Internal error: %s", e)
    if request.path.startswith("/api/"):
        return jsonify({"error": "internal server error"}), 500
    return render_template("dashboard.html", config=load_config()), 500


if __name__ == "__main__":
    logger.info("Web dashboard starting on http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=True)
