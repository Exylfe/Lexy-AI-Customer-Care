"""
Supabase client wrapper — provides two clients:

- `service_client`: uses the service_role key for admin operations
  (billing/usage gatekeeper, RAG document storage). NEVER expose
  this client in the desktop app.
- `anon_client`: uses the anon key scoped by RLS for user-owned reads
  (profile display, document list). Safe for desktop app use.

Both clients are lazily initialized. If Supabase is not configured
(empty SUPABASE_URL), all functions return None gracefully so the
app works without a backend connection.
"""

import logging
from functools import lru_cache

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_service_client():
    """Create the service-role client (cached)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.info("Supabase service client not configured — skipping")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("Supabase service client initialized")
        return client
    except Exception as e:
        logger.warning("Failed to init Supabase service client: %s", e)
        return None


@lru_cache(maxsize=1)
def _get_anon_client():
    """Create the anon/RLS client (cached)."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.info("Supabase anon client not configured — skipping")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        logger.info("Supabase anon client initialized")
        return client
    except Exception as e:
        logger.warning("Failed to init Supabase anon client: %s", e)
        return None


def get_service_client():
    """Get the service-role Supabase client or None."""
    return _get_service_client()


def get_anon_client():
    """Get the anon-key Supabase client or None."""
    return _get_anon_client()


# ─── Profile helpers (service role) ──────────────────────────────

def get_profile(user_id: str) -> dict | None:
    """Fetch a user's profile row by id."""
    client = get_service_client()
    if not client:
        return None
    try:
        resp = client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
        return resp.data
    except Exception as e:
        logger.warning("Failed to fetch profile %s: %s", user_id, e)
        return None


def increment_message_usage(user_id: str) -> int | None:
    """Atomically increment messages_used. Returns new count or None if limit hit."""
    client = get_service_client()
    if not client:
        return None  # No backend = no gatekeeping
    try:
        resp = client.rpc("increment_message_usage", {"user_id": user_id}).execute()
        return resp.data  # int = new count, None = limit reached
    except Exception as e:
        logger.warning("increment_message_usage failed for %s: %s", user_id, e)
        return None  # Fail open or closed? We return None to halt processing.


def match_documents(
    query_embedding: list[float],
    profile_id: str,
    match_count: int = 3,
    match_threshold: float = 0.75,
) -> list[dict] | None:
    """Call match_documents RPC to find relevant knowledge base chunks."""
    client = get_service_client()
    if not client:
        return None
    try:
        resp = client.rpc("match_documents", {
            "query_embedding": query_embedding,
            "match_profile_id": profile_id,
            "match_count": match_count,
            "match_threshold": match_threshold,
        }).execute()
        return resp.data if resp.data else []
    except Exception as e:
        logger.warning("match_documents failed: %s", e)
        return None


def get_document_count(profile_id: str) -> int | None:
    """Count documents for a profile (for server-side quota enforcement)."""
    client = get_service_client()
    if not client:
        return None
    try:
        resp = client.table("documents") \
            .select("id", count="exact") \
            .eq("profile_id", profile_id) \
            .execute()
        return resp.count
    except Exception as e:
        logger.warning("get_document_count failed: %s", e)
        return None


def insert_document_chunks(profile_id: str, chunks: list[dict]) -> bool:
    """Insert document chunks into the documents table.
    Each chunk: {"content": str, "metadata": dict, "embedding": list[float]}
    """
    client = get_service_client()
    if not client:
        return False
    try:
        rows = [
            {
                "profile_id": profile_id,
                "content": c["content"],
                "metadata": c.get("metadata", {}),
                "embedding": c.get("embedding"),
            }
            for c in chunks
        ]
        resp = client.table("documents").insert(rows).execute()
        return bool(resp.data)
    except Exception as e:
        logger.warning("insert_document_chunks failed: %s", e)
        return False


def delete_profile_documents(profile_id: str) -> bool:
    """Delete all document chunks for a profile (e.g. on document deletion)."""
    client = get_service_client()
    if not client:
        return False
    try:
        client.table("documents").delete().eq("profile_id", profile_id).execute()
        return True
    except Exception as e:
        logger.warning("delete_profile_documents failed: %s", e)
        return False
