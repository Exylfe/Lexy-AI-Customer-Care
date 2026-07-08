"""
Lexy Knowledge Base — document upload, text extraction, storage, and quota management.
Supports .txt, .pdf, .docx, .md files. Quota-based upload limits by plan.
"""

import os
import json
import logging
import time
import uuid
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger(__name__)

KB_DIR = os.path.join(DATA_DIR, "knowledge")
INDEX_FILE = os.path.join(KB_DIR, "index.json")

# ─── Quota by plan ───────────────────────────────────────────────

PLAN_QUOTAS = {
    "free": {"max_bytes": 10 * 1024 * 1024, "max_files": 5, "max_file_bytes": 2 * 1024 * 1024},
    "starter": {"max_bytes": 1024 * 1024 * 1024, "max_files": 9999, "max_file_bytes": 50 * 1024 * 1024},
    "pro": {"max_bytes": 10 * 1024 * 1024 * 1024, "max_files": 99999, "max_file_bytes": 100 * 1024 * 1024},
}

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


# ─── Init ────────────────────────────────────────────────────────

def _ensure_kb_dir():
    """Create knowledge/ directory and index if missing."""
    os.makedirs(KB_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "w") as f:
            json.dump([], f)


def _load_index():
    _ensure_kb_dir()
    try:
        with open(INDEX_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_index(index):
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


# ─── Text extraction ─────────────────────────────────────────────

def _extract_text(filepath, ext):
    """Extract text content from a file based on its extension."""
    ext = ext.lower()
    try:
        if ext in (".txt", ".md"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()

        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            text = "\n".join(page.extract_text() for page in reader.pages)
            return text

        elif ext == ".docx":
            from docx import Document
            doc = Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs)

        else:
            return "[Unsupported format]"
    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", filepath, e)
        return f"[Failed to extract text: {e}]"


# ─── Quota ───────────────────────────────────────────────────────

def _get_plan():
    """Read current plan from config. Defaults to 'free'."""
    from lexy_config import load_config
    return load_config().get("billing", {}).get("plan", "free")


def get_quota():
    """Return current usage and limits."""
    plan = _get_plan()
    limits = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])
    index = _load_index()
    used_bytes = sum(f.get("size", 0) for f in index)
    return {
        "plan": plan,
        "used_bytes": used_bytes,
        "max_bytes": limits["max_bytes"],
        "used_files": len(index),
        "max_files": limits["max_files"],
        "max_file_bytes": limits["max_file_bytes"],
    }


# ─── CRUD ────────────────────────────────────────────────────────

def upload_documents(files):
    """Upload multiple files. Returns list of results."""
    from lexy_config import load_config
    config = load_config()
    billing = config.setdefault("billing", {})
    if "plan" not in billing:
        billing["plan"] = "free"
    plan = billing["plan"]
    limits = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])

    _ensure_kb_dir()
    index = _load_index()
    results = []

    current_bytes = sum(f.get("size", 0) for f in index)

    for file in files:
        filename = file.filename.strip()
        if not filename:
            results.append({"file": filename, "status": "error", "error": "Empty filename"})
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({"file": filename, "status": "error", "error": f"Unsupported format: {ext}"})
            continue

        # Read file data
        file_data = file.read()
        file_size = len(file_data)

        # Check per-file size limit
        if file_size > limits["max_file_bytes"]:
            results.append({"file": filename, "status": "error",
                            "error": f"File too large ({file_size / 1024 / 1024:.1f} MB). Max: {limits['max_file_bytes'] / 1024 / 1024:.0f} MB"})
            continue

        # Check total quota
        if current_bytes + file_size > limits["max_bytes"]:
            mb_left = (limits["max_bytes"] - current_bytes) / 1024 / 1024
            results.append({"file": filename, "status": "error",
                            "error": f"Storage full ({mb_left:.1f} MB remaining). Upgrade your plan."})
            continue

        # Check file count
        if len(index) >= limits["max_files"]:
            results.append({"file": filename, "status": "error", "error": "Max file count reached."})
            continue

        # Save
        doc_id = str(uuid.uuid4())[:8]
        safe_name = f"{doc_id}_{filename}"
        dest = os.path.join(KB_DIR, safe_name)

        with open(dest, "wb") as f:
            f.write(file_data)

        # Extract text
        text_content = _extract_text(dest, ext)

        # Index entry
        entry = {
            "id": doc_id,
            "name": filename,
            "size": file_size,
            "type": ext,
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "path": safe_name,
        }
        index.append(entry)
        current_bytes += file_size

        results.append({"file": filename, "status": "ok", "id": doc_id, "size": file_size})

    _save_index(index)
    return results


def list_documents():
    """Return list of uploaded documents (without content)."""
    index = _load_index()
    return [
        {
            "id": d["id"],
            "name": d["name"],
            "size": d["size"],
            "type": d["type"],
            "uploaded_at": d["uploaded_at"],
        }
        for d in index
    ]


def get_document(doc_id):
    """Return document details including extracted text."""
    index = _load_index()
    for entry in index:
        if entry["id"] == doc_id:
            filepath = os.path.join(KB_DIR, entry["path"])
            if not os.path.exists(filepath):
                return None
            ext = entry["type"]
            content = _extract_text(filepath, ext)
            return {
                "id": entry["id"],
                "name": entry["name"],
                "size": entry["size"],
                "type": entry["type"],
                "uploaded_at": entry["uploaded_at"],
                "content": content,
            }
    return None


def delete_document(doc_id):
    """Delete a document by ID."""
    index = _load_index()
    for i, entry in enumerate(index):
        if entry["id"] == doc_id:
            filepath = os.path.join(KB_DIR, entry["path"])
            if os.path.exists(filepath):
                os.remove(filepath)
            index.pop(i)
            _save_index(index)
            return True
    return False


def get_all_knowledge_text(max_chars=50000):
    """Get concatenated text from all documents (for brain context injection)."""
    index = _load_index()
    texts = []
    total = 0
    for entry in index:
        if total >= max_chars:
            break
        filepath = os.path.join(KB_DIR, entry["path"])
        if os.path.exists(filepath):
            ext = entry["type"]
            content = _extract_text(filepath, ext)
            if total + len(content) > max_chars:
                content = content[: max_chars - total]
            texts.append(f"--- Document: {entry['name']} ---\n{content}")
            total += len(content)
    return "\n\n".join(texts)


# ─── Chunking (for RAG, §3 of dev brief) ────────────────────────

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size characters.
    
    The overlap prevents losing context that spans a chunk boundary.
    Chunks are split at sentence boundaries when possible, falling back
    to word boundaries or character position.
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    import re
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Try to break at a sentence boundary
            candidate = text[start:end]
            # Look backwards for sentence enders within the last 30% of the chunk
            search_start = max(len(candidate) - int(chunk_size * 0.3), 0)
            tail = candidate[search_start:]
            # Prefer sentence boundaries
            sentence_match = re.search(r'[.?!]\s(?:[A-Z"])', tail)
            if sentence_match:
                adjust = len(candidate[:search_start]) + sentence_match.end() - 1
                end = start + adjust
            else:
                # Fall back to word boundary
                word_match = re.search(r'\s', tail[::-1])
                if word_match:
                    adjust = len(candidate) - word_match.start()
                    if adjust > int(chunk_size * 0.5):  # Don't make chunks too short
                        adjust = len(candidate)
                    end = start + adjust
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start >= end:
            start = end  # Safety: prevent infinite loop
    return chunks


def sync_document_to_supabase(
    profile_id: str,
    doc_name: str,
    text_content: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> bool:
    """Chunk text, generate embeddings, and insert into Supabase documents table.
    
    This runs server-side only (Flask backend) using the service role key.
    Returns True if all chunks were inserted successfully.
    """
    from embeddings import generate_embeddings_batch

    if not text_content.strip():
        logger.warning("Empty document content — skipping Supabase sync")
        return False

    chunks = chunk_text(text_content, chunk_size=chunk_size, overlap=overlap)
    logger.info("Split '%s' into %d chunks", doc_name, len(chunks))

    # Generate embeddings for all chunks in a batch
    embeddings = generate_embeddings_batch(chunks)
    if embeddings is None:
        logger.warning("Embedding generation failed for '%s' — skipping Supabase", doc_name)
        return False

    if len(embeddings) != len(chunks):
        logger.error(
            "Embedding count mismatch: %d chunks vs %d embeddings",
            len(chunks), len(embeddings),
        )
        return False

    # Build rows
    rows = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        rows.append({
            "content": chunk,
            "metadata": {"source": doc_name, "chunk_index": i},
            "embedding": emb,
        })

    # Insert into Supabase
    from supabase_client import insert_document_chunks
    success = insert_document_chunks(profile_id, rows)
    if success:
        logger.info("Synced %d chunks to Supabase for '%s'", len(rows), doc_name)
    else:
        logger.warning("Failed to sync chunks to Supabase for '%s'", doc_name)
    return success


def delete_profile_documents_local(profile_id: str, doc_name: str | None = None) -> bool:
    """Delete Supabase document chunks for a profile (or specific doc)."""
    from supabase_client import get_service_client
    client = get_service_client()
    if not client:
        return False
    try:
        query = client.table("documents").delete().eq("profile_id", profile_id)
        if doc_name:
            query = query.filter("metadata", "cs", f'"source": "{doc_name}"')
        query.execute()
        return True
    except Exception as e:
        logger.warning("delete_profile_documents failed: %s", e)
        return False
