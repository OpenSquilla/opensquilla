"""Explicit loader for built-in tool adapters.

Historically, importing :mod:`opensquilla.tools.builtin` imported every built-in
tool module directly from ``__init__``. The loader keeps that public behavior
for compatibility, while giving the architecture refactor one named place to
move registration and dependency injection toward.
"""

from __future__ import annotations

import importlib
from types import ModuleType

import structlog

from opensquilla.tools.registry import ToolRegistry, get_default_registry

BUILTIN_TOOL_MODULE_NAMES: tuple[str, ...] = (
    "admin",
    "agents",
    "artifacts",
    "code_exec",
    "filesystem",
    "git",
    "media",
    "messaging",
    "patch",
    "sessions",
    "shell",
    "web",
    "web_fetch",
)

FATAL_BUILTIN_TOOL_MODULES: frozenset[str] = frozenset({"shell", "patch", "filesystem"})

log = structlog.get_logger(__name__)


def import_builtin_tool_modules(
    module_names: tuple[str, ...] = BUILTIN_TOOL_MODULE_NAMES,
) -> dict[str, ModuleType]:
    """Import built-in tool modules and return the modules that loaded.

    Importing the modules still performs legacy ``@tool`` registration against
    the default registry. Keeping that behavior here makes the side effect
    explicit and creates a single future replacement point.
    """

    loaded: dict[str, ModuleType] = {}
    for name in module_names:
        try:
            loaded[name] = importlib.import_module(f"opensquilla.tools.builtin.{name}")
        except Exception as exc:
            if name in FATAL_BUILTIN_TOOL_MODULES:
                raise
            log.warning("builtin_tool.import_failed", module=name, error=str(exc))
    return loaded


def load_builtin_tools(registry: ToolRegistry | None = None) -> list[str]:
    """Load built-in tools into ``registry`` and return the registered names.

    Built-in tool modules currently register themselves with the process-wide
    default registry via decorators. When a custom registry is supplied, this
    function imports the modules, then copies the built-in specs and handlers
    from the default registry into the custom registry. Dynamic tool factories
    such as memory and skill tools remain explicitly registered by their own
    composition code.
    """

    loaded_modules = import_builtin_tool_modules()
    loaded_module_names = {module.__name__ for module in loaded_modules.values()}
    default_registry = get_default_registry()
    target = registry or default_registry
    registered: list[str] = []

    for registered_tool in default_registry.all_tools():
        handler_module = getattr(registered_tool.handler, "__module__", "")
        if handler_module not in loaded_module_names:
            continue
        if target is not default_registry:
            target.register(registered_tool.spec, registered_tool.handler)
        registered.append(registered_tool.spec.name)

    return sorted(set(registered))


__all__ = [
    "BUILTIN_TOOL_MODULE_NAMES",
    "FATAL_BUILTIN_TOOL_MODULES",
    "import_builtin_tool_modules",
    "load_builtin_tools",
]
