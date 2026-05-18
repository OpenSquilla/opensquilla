from __future__ import annotations

from opensquilla.engine.runtime import TurnRunner
from opensquilla.tools.registry import ToolRegistry
from opensquilla.tools.types import CallerKind, InteractionMode, ToolContext, ToolSpec


async def _handler() -> str:
    return "ok"


def _spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name} tool", parameters={})


def test_owner_cron_tool_policy_uses_runtime_registry_names() -> None:
    registry = ToolRegistry()
    for name in ("session_status", "memory_search", "exec_command", "web_fetch"):
        registry.register(_spec(name), _handler)
    runner = TurnRunner(
        provider_selector=None,
        tool_registry=registry,
        session_manager=object(),
        config=object(),
    )
    ctx = ToolContext(
        is_owner=True,
        caller_kind=CallerKind.CRON,
        interaction_mode=InteractionMode.UNATTENDED,
        session_key="cron:owner:run:1",
        tool_policy={
            "profile": "minimal",
            "also_allow": ["memory_search", "exec_command"],
            "deny": ["web_fetch"],
        },
    )

    tool_defs, _handler_fn = runner._build_tools(ctx)
    names = {tool.name for tool in tool_defs}

    assert "session_status" in names
    assert "memory_search" in names
    assert "exec_command" in names
    assert "web_fetch" not in names
