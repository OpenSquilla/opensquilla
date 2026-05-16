from __future__ import annotations

from opensquilla.tools.builtin import load_builtin_tools
from opensquilla.tools.registry import ToolRegistry, get_default_registry


def test_load_builtin_tools_registers_default_builtin_surface() -> None:
    names = set(load_builtin_tools())
    registry = get_default_registry()

    assert {"read_file", "exec_command", "sessions_spawn", "web_fetch"} <= names
    assert registry.get("read_file") is not None
    assert registry.get("exec_command") is not None


def test_load_builtin_tools_can_copy_builtin_surface_to_custom_registry() -> None:
    registry = ToolRegistry()

    names = set(load_builtin_tools(registry))

    assert {"read_file", "exec_command", "sessions_spawn", "web_fetch"} <= names
    assert registry.get("read_file") is not None
    assert registry.get("exec_command") is not None
    assert registry.get("memory_save") is None
