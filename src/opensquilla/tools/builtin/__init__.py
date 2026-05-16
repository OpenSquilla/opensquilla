"""Register all built-in tools by importing each submodule."""

from __future__ import annotations

from opensquilla.tools.builtin.loader import (
    BUILTIN_TOOL_MODULE_NAMES,
    import_builtin_tool_modules,
    load_builtin_tools,
)

globals().update(import_builtin_tool_modules())

__all__ = [
    *BUILTIN_TOOL_MODULE_NAMES,
    "BUILTIN_TOOL_MODULE_NAMES",
    "import_builtin_tool_modules",
    "load_builtin_tools",
]
