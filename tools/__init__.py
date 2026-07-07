"""
Tools are auto-discovered from the tools/ directory.
Each tool module must expose:
- SCHEMA: an OpenAI-style function schema dict describing the tool
- run(**kwargs): the actual Python function that executes it

To add a new ability: create a new file in tools/ with SCHEMA + run().
It will be automatically available to the LLM — no registration needed.
"""

import importlib
import logging
import os
import pkgutil

logger = logging.getLogger(__name__)

TOOLS = {}


def _discover_tools():
    """Import every module in the tools/ package and register if it has SCHEMA + run."""
    package = __name__
    for importer, modname, ispkg in pkgutil.iter_modules(
        path=__path__, prefix=f"{package}."
    ):
        if modname == __name__ or ispkg:
            continue
        try:
            mod = importlib.import_module(modname)
            if hasattr(mod, "SCHEMA") and hasattr(mod, "run"):
                name = mod.SCHEMA.get("name", modname.split(".")[-1])
                TOOLS[name] = mod
                logger.debug("Discovered tool: %s", name)
        except Exception as e:
            logger.warning("Failed to load tool module %s: %s", modname, e)


_discover_tools()


def get_schemas():
    """Return the list of tool schemas to send to the LLM."""
    return [{"type": "function", "function": mod.SCHEMA} for mod in TOOLS.values()]


def call_tool(name, arguments):
    """Look up a tool by name and run it with the given arguments dict."""
    if name not in TOOLS:
        logger.warning("Unknown tool called: %s", name)
        return f"Error: no tool named '{name}'"
    try:
        result = TOOLS[name].run(**arguments)
        logger.info("Tool %s returned (%.100s)", name, str(result))
        return result
    except Exception as e:
        logger.exception("Error running tool '%s'", name)
        return f"Error running tool '{name}': {e}"
