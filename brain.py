import json
import logging
import httpx

from config import (
    PROVIDERS,
    SYSTEM_PROMPT,
    COMMAND_PROMPT,
    TELEGRAM_BOT_TOKEN,
    EMBEDDING_API_KEY,
)
from memory import load_history, save_history
from tools import get_schemas, call_tool

logger = logging.getLogger(__name__)


def _apply_config_api_keys(config):
    """Override provider API keys from config (with env var fallback)."""
    import os
    apikeys = config.get("api_keys", {})
    for provider in PROVIDERS:
        name = provider["name"].lower()
        if name == "groq":
            provider["api_key"] = apikeys.get("groq") or os.environ.get("GROQ_API_KEY", "")
        elif name == "google":
            provider["api_key"] = apikeys.get("google") or os.environ.get("GOOGLE_API_KEY", "")
    # Telegram
    tk = apikeys.get("telegram") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tk:
        global TELEGRAM_BOT_TOKEN
        TELEGRAM_BOT_TOKEN = tk


def _build_prompt(sender=None, admin_mode=False):
    """Build dynamic system prompt merging static prompts with lexy_settings.json config."""
    from lexy_config import load_config

    # Pick base prompt based on admin mode
    if admin_mode:
        logger.info("Admin mode activated for sender %s", sender)
        base = COMMAND_PROMPT
    else:
        base = SYSTEM_PROMPT

    config = load_config()

    # Override provider API keys with config-stored keys (env fallback)
    _apply_config_api_keys(config)
    business = config.get("business", {})
    personality = config.get("personality", {})
    hours = config.get("hours", {})
    sections = [base]

    # ── Business info ──
    biz_name = business.get("name", "").strip()
    biz_type = business.get("type", "").strip()
    biz_desc = business.get("description", "").strip()
    if biz_name or biz_type or biz_desc:
        biz_block = "\n\nYOUR BUSINESS (configured in Settings):\n"
        if biz_name:
            biz_block += f"- Business name: {biz_name}\n"
        if biz_type:
            biz_block += f"- Business type: {biz_type}\n"
        if biz_desc:
            biz_block += f"- What you offer: {biz_desc}\n"
        biz_block += (
            "- When a customer asks about your business, describe it accurately "
            "using the info above.\n"
        )
        sections.append(biz_block)

    # ── Knowledge Base (uploaded docs) ──
    try:
        from knowledge_base import get_all_knowledge_text
        kb_text = get_all_knowledge_text(max_chars=30000)
        if kb_text:
            sections.append(
                "\n\nKNOWLEDGE BASE (documents uploaded by the business):\n"
                "The business has uploaded reference documents. Use this information "
                "to answer customer questions accurately.\n\n"
                + kb_text
            )
    except Exception as e:
        logger.warning("Failed to load knowledge base: %s", e)

    # ── Personality overrides ──
    tone = personality.get("tone", 0)
    use_emojis = personality.get("use_emojis", True)
    response_len = personality.get("response_length", 0)
    greeting_type = personality.get("greeting_type", "auto")
    greeting_custom = personality.get("greeting_custom", "").strip()

    pers_block = "\nRESPONSE STYLE (configured in Settings):\n"
    if tone <= -30:
        pers_block += "- Tone: Very friendly, warm, and casual. Use enthusiasm.\n"
    elif tone >= 30:
        pers_block += "- Tone: Professional, formal, and polished.\n"
    else:
        pers_block += "- Tone: Balanced — friendly but professional.\n"

    pers_block += f"- Use emojis: {'YES' if use_emojis else 'NO'}\n"

    if response_len <= -30:
        pers_block += "- Response length: Brief — short and direct.\n"
    elif response_len >= 30:
        pers_block += "- Response length: Detailed — thorough explanations.\n"
    else:
        pers_block += "- Response length: Moderate.\n"

    if greeting_type == "custom" and greeting_custom:
        pers_block += f"- Your standard greeting: \"{greeting_custom}\"\n"

    sections.append(pers_block)

    # ── Working hours ──
    open_days = [
        d.capitalize()
        for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        if hours.get(d, {}).get("open")
    ]
    closed_msg = hours.get("closed_message", "").strip()

    if open_days or closed_msg:
        hr_block = "\nWORKING HOURS (configured in Settings):\n"
        if open_days:
            hr_block += f"- Available days: {', '.join(open_days)}\n"
            for day_name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
                day = hours.get(day_name, {})
                if day.get("open"):
                    hr_block += f"  {day_name.capitalize()}: {day.get('from', '?')} — {day.get('to', '?')}\n"
        hr_block += (
            "- If a customer messages OUTSIDE these hours, politely say "
            "you're currently closed and mention when you'll be open next.\n"
        )
        if closed_msg:
            hr_block += f"- Default closed message: \"{closed_msg}\"\n"
        sections.append(hr_block)

    return "\n".join(sections)


def _try_provider(messages, provider):
    """Send messages to one provider. Returns (reply_text | None, tool_loop_exhausted)."""
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }

    url = provider["url"]
    model = provider["model"]

    # Google Gemini uses a different API format — handle separately
    if "google" in provider["name"].lower():
        return _try_google_gemini(messages, provider)

    for attempt in range(5):
        payload = {
            "model": model,
            "messages": messages,
            "tools": get_schemas(),
        }
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(
                    "%s API error: %s %s",
                    provider["name"],
                    resp.status_code,
                    resp.text,
                )
                return None, False
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(
                "%s %s (attempt %d/5): %s",
                provider["name"],
                type(e).__name__,
                attempt + 1,
                e,
            )
            if attempt == 4:
                return None, False
            continue

        data = resp.json()
        choice = data["choices"][0]["message"]
        messages.append(choice)

        tool_calls = choice.get("tool_calls")
        if not tool_calls:
            return choice.get("content", ""), False

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            logger.info("Tool call: %s %s", name, args)
            result = call_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": name,
                "content": str(result),
            })

    logger.warning("Tool call loop exhausted for %s", provider["name"])
    return None, True


def _try_google_gemini(messages, provider):
    """Handle Google Gemini API which uses a different format."""
    try:
        # Extract the system prompt and convert to Gemini format
        system_content = ""
        gemini_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] in ("user", "assistant", "model"):
                role = "model" if msg["role"] in ("assistant", "model") else "user"
                gemini_messages.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}],
                })
            elif msg["role"] == "tool":
                gemini_messages.append({
                    "role": "user",
                    "parts": [{"text": f"Tool result: {msg['content']}"}],
                })

        payload = {
            "contents": gemini_messages,
            "systemInstruction": {
                "parts": [{"text": system_content}]
            },
        }

        headers = {
            "Content-Type": "application/json",
        }
        url = f"{provider['url']}?key={provider['api_key']}"

        with httpx.Client(timeout=60) as client:
            resp = client.post(url, headers=headers, json=payload)

        if resp.status_code != 200:
            logger.error(
                "%s API error: %s %s",
                provider["name"],
                resp.status_code,
                resp.text,
            )
            return None, False

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            logger.error("%s: no candidates in response", provider["name"])
            return None, False

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return text, False

    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("%s %s: %s", provider["name"], type(e).__name__, e)
        return None, False


def chat(user_message, history=None, sender=None, admin_mode=False, profile_id=None):
    """Send a user message through the LLM, trying providers in order.
    Falls back to the next provider if one fails. `sender` is an
    optional identifier (e.g., WhatsApp number) used for memory and
    command-mode detection. `profile_id` is the Supabase user UUID for
    usage tracking and RAG (used server-side only).
    """
    # ── Message usage gatekeeper (server-side only) ──────────────
    if profile_id:
        from supabase_client import increment_message_usage
        new_count = increment_message_usage(profile_id)
        if new_count is None:
            logger.warning(
                "Message limit reached for profile %s — rejecting",
                profile_id,
            )
            return (
                "I'm sorry, but you've reached your message limit for this "
                "billing cycle. Please upgrade your plan to continue using Lexy."
            )

    # ── RAG: retrieve relevant knowledge base content ──────────
    rag_context = None
    if profile_id and EMBEDDING_API_KEY:
        try:
            from embeddings import generate_embedding
            from supabase_client import match_documents
            query_embedding = generate_embedding(user_message)
            if query_embedding:
                matches = match_documents(query_embedding, profile_id)
                if matches:
                    rag_context = "\n\n".join(
                        f"[Relevant knowledge snippet] {m['content']}"
                        for m in matches
                    )
                    logger.info(
                        "RAG: found %d relevant snippets for profile %s",
                        len(matches), profile_id,
                    )
        except Exception as e:
            logger.warning("RAG pipeline failed: %s", e)

    persist = history is None
    if history is None:
        history = load_history(sender)

    prompt = _build_prompt(sender, admin_mode=admin_mode)

    # ── Inject RAG context into system prompt ────────────────────
    if rag_context:
        prompt += (
            "\n\nREFERENCE DOCUMENTS (ground your answers in these before using general knowledge):\n"
            + rag_context
            + "\n\nIf the reference documents contain relevant information, prioritize it over "
            "your general knowledge. If no references are relevant, answer normally."
        )

    messages = [{"role": "system", "content": prompt}] + history
    messages.append({"role": "user", "content": user_message})

    last_error = None

    for provider in PROVIDERS:
        if not provider.get("api_key"):
            logger.info("Skipping %s: no API key", provider["name"])
            continue

        logger.info("Trying provider: %s (%s)", provider["name"], provider["model"])
        reply, exhausted = _try_provider(messages.copy(), provider)

        if reply is not None:
            # Success — persist and return
            if persist:
                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": reply})
                save_history(history, sender)
            return reply

        # Provider failed — log and try next
        logger.warning(
            "Provider %s failed%s",
            provider["name"],
            " (tool loop exhausted)" if exhausted else "",
        )
        last_error = f"{provider['name']} failed"

    # All providers exhausted
    logger.error("All providers failed for sender=%s", sender)
    return f"Sorry, no AI provider is available right now. ({last_error})"
