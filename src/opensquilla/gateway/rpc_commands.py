"""Slash-command catalog RPC.

Exposes :data:`opensquilla.engine.commands.DEFAULT_REGISTRY` to non-Python
surfaces (initially the web frontend) so the slash-menu list comes from
one source rather than being hardcoded per-surface. Read-only.
"""

from __future__ import annotations

from typing import Any

from opensquilla.engine.commands import DEFAULT_REGISTRY, CommandDef, Surface, parse_surface
from opensquilla.gateway.rpc import RpcContext, get_dispatcher

_d = get_dispatcher()


def _serialize(cmd: CommandDef, surface: Surface) -> dict[str, Any]:
    """Project a CommandDef into a JSON-safe dict.

    ``rpc_params`` is intentionally omitted — it has no JSON representation
    and is only meaningful inside in-process executors.
    """
    execution = cmd.execution_for(surface)
    if execution is None:
        raise ValueError(f"{cmd.name} is not visible on {surface.value}")
    out: dict[str, Any] = {
        "name": cmd.name,
        "usage": cmd.usage,
        "description": cmd.description,
        "aliases": list(cmd.aliases),
        "argument_choices": [
            {"value": choice.value, "description": choice.description}
            for choice in cmd.argument_choices
        ],
        "execution": {
            "kind": execution.kind.value,
            "action": execution.action,
        },
    }
    if execution.rpc_method is not None:
        out["execution"]["rpc_method"] = execution.rpc_method
        out["rpc_method"] = execution.rpc_method
    return out


@_d.method("commands.list_for_surface", scope="operator.read")
async def _handle_commands_list_for_surface(
    params: dict | None, _ctx: RpcContext
) -> dict[str, Any]:
    raw = (params or {}).get("surface", "web")
    if not isinstance(raw, str):
        raise ValueError("params.surface must be a string")
    try:
        surface = parse_surface(raw)
    except ValueError as exc:
        valid = ", ".join(sorted({s.value for s in Surface}))
        raise ValueError(f"unknown surface {raw!r}; valid: {valid}") from exc
    return {
        "surface": surface.value,
        "commands": [_serialize(cmd, surface) for cmd in DEFAULT_REGISTRY.for_surface(surface)],
    }
