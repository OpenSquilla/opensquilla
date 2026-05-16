from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.memory.source_rpc import (
    memory_source_list_rpc_payload,
    memory_source_search_rpc_payload,
    memory_source_show_rpc_payload,
)
from opensquilla.memory.types import MemorySearchResult, MemorySource, SearchIntent

ROOT = Path(__file__).resolve().parents[1]
RPC_MEMORY = ROOT / "src/opensquilla/gateway/rpc_memory.py"


@dataclass
class FakeMemoryManager:
    workspace_dir: Path | None
    memory_config: Any = field(
        default_factory=lambda: SimpleNamespace(index_captured_turns=False)
    )
    search_calls: list[tuple[str, Any, Any]] = field(default_factory=list)

    async def search(self, query: str, opts: Any, *, intent: Any) -> list[MemorySearchResult]:
        self.search_calls.append((query, opts, intent))
        return [
            MemorySearchResult(
                chunk_id="chunk-1",
                path="memory/a.md",
                source=MemorySource.memory,
                start_line=1,
                end_line=2,
                snippet="alpha snippet",
                score=0.9,
                vector_score=0.8,
                text_score=0.7,
                chunk_hash="hash-1",
                citation="memory/a.md#L1-L2",
            )
        ]


def _resolver(manager: FakeMemoryManager):
    def resolve(agent_id: str | None) -> tuple[str, FakeMemoryManager]:
        return (agent_id or "main", manager)

    return resolve


def _imports_from(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_memory_source_list_rpc_payload_preserves_wire_shape(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("root\n", encoding="utf-8")
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "a.md").write_text("one\ntwo\n", encoding="utf-8")
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    payload = memory_source_list_rpc_payload({"agentId": "ops"}, _resolver(manager))

    assert payload["agentId"] == "ops"
    assert payload["count"] == 2
    assert [row["path"] for row in payload["files"]] == ["MEMORY.md", "memory/a.md"]
    assert payload["files"][1]["lineCount"] == 2


@pytest.mark.asyncio
async def test_memory_source_search_rpc_payload_preserves_wire_shape_and_params(
    tmp_path: Path,
) -> None:
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    payload = await memory_source_search_rpc_payload(
        {"query": " alpha ", "agentId": "ops", "limit": 3, "minScore": "0.25"},
        _resolver(manager),
    )

    assert payload["agentId"] == "ops"
    assert payload["query"] == "alpha"
    assert payload["count"] == 1
    assert payload["results"][0]["chunkId"] == "chunk-1"
    assert payload["results"][0]["citation"] == "memory/a.md#L1-L2"
    assert manager.search_calls[0][0] == "alpha"
    assert manager.search_calls[0][1].max_results == 3
    assert manager.search_calls[0][1].min_score == 0.25
    assert manager.search_calls[0][2] is SearchIntent.ADMIN


def test_memory_source_show_rpc_payload_preserves_wire_shape(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "a.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    payload = memory_source_show_rpc_payload(
        {"path": "memory/a.md", "fromLine": 2, "lines": 1},
        _resolver(manager),
    )

    assert payload == {
        "agentId": "main",
        "path": "memory/a.md",
        "fromLine": 2,
        "lineCount": 1,
        "truncated": False,
        "content": "two",
    }


@pytest.mark.asyncio
async def test_memory_source_rpc_payloads_validate_request_shape(tmp_path: Path) -> None:
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    with pytest.raises(ValueError, match="params must be an object"):
        memory_source_list_rpc_payload("bad-params", _resolver(manager))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="params must be an object"):
        await memory_source_search_rpc_payload(None, _resolver(manager))
    with pytest.raises(ValueError, match="params.query is required"):
        await memory_source_search_rpc_payload({}, _resolver(manager))
    with pytest.raises(ValueError, match="params.limit must be <= 20"):
        await memory_source_search_rpc_payload(
            {"query": "alpha", "limit": 21},
            _resolver(manager),
        )
    with pytest.raises(ValueError, match="params must be an object"):
        memory_source_show_rpc_payload(None, _resolver(manager))
    with pytest.raises(ValueError, match="params.lines must be <= 500"):
        memory_source_show_rpc_payload(
            {"path": "memory/a.md", "lines": 501},
            _resolver(manager),
        )


def test_gateway_delegates_memory_rpc_payloads_to_memory_boundary() -> None:
    imports = _imports_from(RPC_MEMORY)
    top_level_functions = _top_level_functions(RPC_MEMORY)

    assert (
        "opensquilla.memory.source_rpc",
        "memory_source_list_rpc_payload",
    ) in imports
    assert (
        "opensquilla.memory.source_rpc",
        "memory_source_search_rpc_payload",
    ) in imports
    assert (
        "opensquilla.memory.source_rpc",
        "memory_source_show_rpc_payload",
    ) in imports
    assert "_memory_source_row_to_wire" not in top_level_functions
    assert "_memory_source_search_row_to_wire" not in top_level_functions
    assert "_memory_source_content_to_wire" not in top_level_functions
    assert "_int_param" not in top_level_functions


@pytest.mark.asyncio
async def test_gateway_preserves_memory_source_unavailable_error() -> None:
    from opensquilla.gateway.rpc import RpcContext, get_dispatcher

    result = await get_dispatcher().dispatch(
        "r1",
        "memory.list",
        {"agentId": "main"},
        RpcContext(
            conn_id="test",
            memory_managers={"main": FakeMemoryManager(workspace_dir=None)},
        ),
    )

    assert result.error is not None
    assert result.error.code == "UNAVAILABLE"
