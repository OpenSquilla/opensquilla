"""RPC payload builders for memory source inspection surfaces."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from opensquilla.memory.source_inspection import (
    MEMORY_SOURCE_MAX_SHOW_LINES,
    MemorySourceContent,
    MemorySourceRow,
    list_memory_source_rows,
    read_memory_source_content,
)
from opensquilla.memory.source_search import (
    MEMORY_SOURCE_SEARCH_DEFAULT_RESULTS,
    MEMORY_SOURCE_SEARCH_MAX_RESULTS,
    MemorySourceSearchRow,
    search_memory_sources,
)

type MemoryManagerResolver = Callable[[str | None], tuple[str, Any]]


class MemorySourceUnavailableError(RuntimeError):
    """Raised when a memory source RPC payload cannot reach source storage."""


def memory_source_list_rpc_payload(
    params: Mapping[str, Any] | None,
    resolve_manager: MemoryManagerResolver,
) -> dict[str, Any]:
    """Build the RPC wire payload for memory source listing."""

    raw = _memory_rpc_params(params, allow_none=True)
    agent_id, manager = resolve_manager(_agent_id_param(raw))
    rows = [
        _memory_source_row_to_wire(row)
        for row in list_memory_source_rows(_memory_root(manager))
    ]
    return {"agentId": agent_id, "count": len(rows), "files": rows}


async def memory_source_search_rpc_payload(
    params: Mapping[str, Any] | None,
    resolve_manager: MemoryManagerResolver,
) -> dict[str, Any]:
    """Build the RPC wire payload for memory source search."""

    raw = _memory_rpc_params(params)
    query = str(raw.get("query") or "").strip()
    if not query:
        raise ValueError("params.query is required")
    limit = _int_param(
        raw,
        "limit",
        MEMORY_SOURCE_SEARCH_DEFAULT_RESULTS,
        minimum=1,
        maximum=MEMORY_SOURCE_SEARCH_MAX_RESULTS,
    )
    try:
        min_score = float(raw.get("minScore", 0.0) or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("params.minScore must be a number") from exc

    agent_id, manager = resolve_manager(_agent_id_param(raw))
    results = await search_memory_sources(
        manager,
        query,
        max_results=limit,
        min_score=min_score,
    )
    rows = [_memory_source_search_row_to_wire(row) for row in results]
    return {"agentId": agent_id, "query": query, "count": len(rows), "results": rows}


def memory_source_show_rpc_payload(
    params: Mapping[str, Any] | None,
    resolve_manager: MemoryManagerResolver,
) -> dict[str, Any]:
    """Build the RPC wire payload for memory source content inspection."""

    raw = _memory_rpc_params(params)
    raw_path = str(raw.get("path") or "")
    agent_id, manager = resolve_manager(_agent_id_param(raw))

    memory_config = getattr(manager, "memory_config", None)
    allow_archive = bool(memory_config and getattr(memory_config, "index_captured_turns", False))

    from_line = raw.get("fromLine")
    if from_line is not None:
        from_line = _int_param(raw, "fromLine", 1, minimum=1, maximum=1_000_000)
    lines = raw.get("lines")
    if lines is not None:
        lines = _int_param(
            raw,
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


def _memory_rpc_params(
    params: Mapping[str, Any] | None,
    *,
    allow_none: bool = False,
) -> Mapping[str, Any]:
    if params is None and allow_none:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")
    return params


def _agent_id_param(params: Mapping[str, Any]) -> str | None:
    agent_id = params.get("agentId")
    return str(agent_id) if agent_id is not None else None


def _int_param(
    params: Mapping[str, Any],
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


def _memory_root(manager: Any) -> Path:
    root = getattr(manager, "workspace_dir", None) or getattr(manager, "memory_dir", None)
    if root is None:
        raise MemorySourceUnavailableError("Memory workspace directory is not configured")
    return Path(root)


def _memory_source_search_row_to_wire(row: MemorySourceSearchRow) -> dict[str, Any]:
    return {
        "chunkId": row.chunk_id,
        "path": row.path,
        "source": row.source,
        "startLine": row.start_line,
        "endLine": row.end_line,
        "snippet": row.snippet,
        "score": row.score,
        "vectorScore": row.vector_score,
        "textScore": row.text_score,
        "chunkHash": row.chunk_hash,
        "citation": row.citation,
    }


def _memory_source_row_to_wire(row: MemorySourceRow) -> dict[str, Any]:
    return {
        "path": row.path,
        "sizeBytes": row.size_bytes,
        "modifiedAt": row.modified_at,
        "lineCount": row.line_count,
    }


def _memory_source_content_to_wire(
    agent_id: str,
    content: MemorySourceContent,
) -> dict[str, Any]:
    return {
        "agentId": agent_id,
        "path": content.path,
        "fromLine": content.from_line,
        "lineCount": content.line_count,
        "truncated": content.truncated,
        "content": content.content,
    }
