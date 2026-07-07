import os
import logging

from config import DATA_DIR

logger = logging.getLogger(__name__)

# All file operations are sandboxed to this folder so the assistant
# can never read/write anywhere else on your machine.
WORKSPACE = os.path.join(DATA_DIR, "workspace")
os.makedirs(WORKSPACE, exist_ok=True)

SCHEMA = {
    "name": "file_access",
    "description": (
        "Read or write a text file inside the assistant's local workspace folder. "
        "Use action='read' to read a file, action='write' to create/overwrite one, "
        "or action='list' to see all files."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["read", "write", "list"]},
            "filename": {"type": "string", "description": "Name of the file, e.g. 'notes.txt'"},
            "content": {"type": "string", "description": "Content to write (only for action='write')"},
        },
        "required": ["action"],
    },
}


def _safe_path(filename):
    path = os.path.normpath(os.path.join(WORKSPACE, filename))
    if not path.startswith(os.path.normpath(WORKSPACE)):
        raise PermissionError("Access denied: path escapes workspace.")
    return path


def run(action, filename=None, content=None):
    if action == "list":
        files = os.listdir(WORKSPACE)
        if not files:
            return "Workspace is empty."
        return "Files in workspace:\n" + "\n".join(f"  {f}" for f in sorted(files))

    if not filename:
        return "Error: filename is required for read/write."

    path = _safe_path(filename)

    if action == "read":
        if not os.path.exists(path):
            return f"File '{filename}' does not exist."
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    if action == "write":
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or "")
        logger.info("Wrote %d bytes to workspace/%s", len(content or ""), filename)
        return f"Saved to '{filename}'."

    return f"Unknown action '{action}'."
