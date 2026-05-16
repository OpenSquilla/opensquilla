"""RPC handlers for read-only memory inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opensquilla.gateway.rpc import RpcContext, RpcUnavailableError, get_dispatcher
from opensquilla.memory.source_inspection import (
    MEMORY_SOURCE_MAX_SHOW_LINES,
    MemorySourceContent,
    MemorySourceRow,
    list_memory_source_rows,
    read_memory_source_content,
)
from opensquilla.memory.types import MemorySearchOpts, SearchIntent
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


def _int_param(
    params: dict[str, Any],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = params.get(name, default)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"params.{name} must be an integer") from exc
    if number < minimum:
        raise ValueError(f"params.{name} must be >= {minimum}")
    if number > maximum:
        raise ValueError(f"params.{name} must be <= {maximum}")
    return number


def _result_to_wire(result: Any) -> dict[str, Any]:
    source = getattr(result, "source", "")
    source_value = getattr(source, "value", source)
    return {
        "chunkId": getattr(result, "chunk_id", ""),
        "path": getattr(result, "path", ""),
        "source": str(source_value),
        "startLine": getattr(result, "start_line", 0),
        "endLine": getattr(result, "end_line", 0),
        "snippet": getattr(result, "snippet", ""),
        "score": getattr(result, "score", 0.0),
        "vectorScore": getattr(result, "vector_score", None),
        "textScore": getattr(result, "text_score", None),
        "chunkHash": getattr(result, "chunk_hash", None),
        "citation": getattr(result, "citation", None),
    }


def _memory_source_row_to_wire(row: MemorySourceRow) -> dict[str, Any]:
    return {
        "path": row.path,
        "sizeBytes": row.size_bytes,
        "modifiedAt": row.modified_at,
        "lineCount": row.line_count,
    }


def _memory_source_content_to_wire(agent_id: str, content: MemorySourceContent) -> dict[str, Any]:
    return {
        "agentId": agent_id,
        "path": content.path,
        "fromLine": content.from_line,
        "lineCount": content.line_count,
        "truncated": content.truncated,
        "content": content.content,
    }


@_d.method("memory.list", scope="operator.read")
async def _handle_memory_list(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    if params is not None and not isinstance(params, dict):
        raise ValueError("params must be an object")
    agent_id, manager = _require_memory_manager(ctx, (params or {}).get("agentId"))
    root = _memory_root(manager)
    rows = [_memory_source_row_to_wire(row) for row in list_memory_source_rows(root)]
    return {"agentId": agent_id, "count": len(rows), "files": rows}


@_d.method("memory.search", scope="operator.read")
async def _handle_memory_search(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    query = str(params.get("query") or "").strip()
    if not query:
        raise ValueError("params.query is required")
    limit = _int_param(params, "limit", 10, minimum=1, maximum=20)
    try:
        min_score = float(params.get("minScore", 0.0) or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("params.minScore must be a number") from exc

    agent_id, manager = _require_memory_manager(ctx, params.get("agentId"))
    opts = MemorySearchOpts(max_results=limit, min_score=min_score)
    results = await manager.search(query, opts, intent=SearchIntent.ADMIN)
    rows = [_result_to_wire(result) for result in results]
    return {"agentId": agent_id, "query": query, "count": len(rows), "results": rows}


def _memory_root(manager: Any) -> Path:
    root = getattr(manager, "workspace_dir", None) or getattr(manager, "memory_dir", None)
    if root is None:
        raise RpcUnavailableError("Memory workspace directory is not configured")
    return Path(root)


@_d.method("memory.show", scope="operator.read")
async def _handle_memory_show(params: dict | None, ctx: RpcContext) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    raw_path = str(params.get("path") or "")
    agent_id, manager = _require_memory_manager(ctx, params.get("agentId"))

    memory_config = getattr(manager, "memory_config", None)
    allow_archive = bool(memory_config and getattr(memory_config, "index_captured_turns", False))

    from_line = params.get("fromLine")
    if from_line is not None:
        from_line = _int_param(params, "fromLine", 1, minimum=1, maximum=1_000_000)
    lines = params.get("lines")
    if lines is not None:
        lines = _int_param(
            params,
            "lines",
            1,
            minimum=1,
            maximum=MEMORY_SOURCE_MAX_SHOW_LINES,
        )

    content = read_memory_source_content(
        _memory_root(manager),
        raw_path,
        from_line=from_line,
        lines=lines,
        allow_archive=allow_archive,
    )
    return _memory_source_content_to_wire(agent_id, content)
