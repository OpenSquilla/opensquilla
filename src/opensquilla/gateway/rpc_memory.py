"""RPC handlers for read-only memory inspection."""

from __future__ import annotations

from typing import Any, NoReturn

from opensquilla.gateway.rpc import RpcContext, RpcUnavailableError, get_dispatcher
from opensquilla.memory.source_rpc import (
    MemorySourceUnavailableError,
    memory_source_list_rpc_payload,
    memory_source_search_rpc_payload,
    memory_source_show_rpc_payload,
)
from opensquilla.session.keys import normalize_agent_id

_d = get_dispatcher()


def _require_memory_manager(ctx: RpcContext, agent_id: str | None) -> tuple[str, Any]:
    managers = getattr(ctx, "memory_managers", None) or {}
    if not managers:
        raise RpcUnavailableError("No memory managers configured")
    resolved_agent = normalize_agent_id(agent_id or "main")
    manager = managers.get(resolved_agent)
    if manager is None:
        raise KeyError(f"Memory manager not found for agent: {resolved_agent}")
    return resolved_agent, manager


def _resolve_memory_source_unavailable(exc: MemorySourceUnavailableError) -> NoReturn:
    raise RpcUnavailableError(str(exc)) from exc


@_d.method("memory.list", scope="operator.read")
async def _handle_memory_list(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    try:
        return memory_source_list_rpc_payload(
            params,
            lambda agent_id: _require_memory_manager(ctx, agent_id),
        )
    except MemorySourceUnavailableError as exc:
        _resolve_memory_source_unavailable(exc)


@_d.method("memory.search", scope="operator.read")
async def _handle_memory_search(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    try:
        return await memory_source_search_rpc_payload(
            params,
            lambda agent_id: _require_memory_manager(ctx, agent_id),
        )
    except MemorySourceUnavailableError as exc:
        _resolve_memory_source_unavailable(exc)


@_d.method("memory.show", scope="operator.read")
async def _handle_memory_show(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    try:
        return memory_source_show_rpc_payload(
            params,
            lambda agent_id: _require_memory_manager(ctx, agent_id),
        )
    except MemorySourceUnavailableError as exc:
        _resolve_memory_source_unavailable(exc)
