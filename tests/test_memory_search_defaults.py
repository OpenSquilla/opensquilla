from __future__ import annotations

from types import SimpleNamespace

import pytest

from opensquilla.memory.types import MemorySearchResult, MemorySource, SearchIntent
from opensquilla.tools.builtin.memory_tools import create_memory_tools
from opensquilla.tools.registry import ToolRegistry


class _FakeRetriever:
    def __init__(self) -> None:
        self.calls = []

    async def search(self, query, opts, *, intent):
        self.calls.append((query, opts, intent))
        return [
            MemorySearchResult(
                chunk_id="chunk-1",
                path="MEMORY.md",
                source=MemorySource.memory,
                start_line=1,
                end_line=1,
                snippet="alpha",
                score=0.9,
                text="alpha",
            )
        ]


@pytest.mark.asyncio
async def test_memory_search_tool_uses_bundled_defaults(tmp_path):
    registry = ToolRegistry()
    retriever = _FakeRetriever()
    create_memory_tools(
        stores=SimpleNamespace(),
        retrievers=retriever,
        memory_dir=str(tmp_path),
        registry=registry,
    )

    registered = registry.get("memory_search")
    assert registered is not None
    await registered.handler(query="alpha")

    assert retriever.calls
    _query, opts, intent = retriever.calls[0]
    assert intent is SearchIntent.TOOL
    assert opts.max_results == 6
    assert opts.min_score == 0.35


@pytest.mark.asyncio
async def test_memory_search_tool_allows_explicit_min_score_override(tmp_path):
    registry = ToolRegistry()
    retriever = _FakeRetriever()
    create_memory_tools(
        stores=SimpleNamespace(),
        retrievers=retriever,
        memory_dir=str(tmp_path),
        registry=registry,
    )

    registered = registry.get("memory_search")
    assert registered is not None
    await registered.handler(query="alpha", max_results=4, min_score=0.0)

    _query, opts, _intent = retriever.calls[0]
    assert opts.max_results == 4
    assert opts.min_score == 0.0


def test_memory_tool_descriptions_name_nested_memory_sources(tmp_path):
    registry = ToolRegistry()
    create_memory_tools(
        stores=SimpleNamespace(),
        retrievers=_FakeRetriever(),
        memory_dir=str(tmp_path),
        registry=registry,
    )

    memory_search = registry.get("memory_search")
    memory_get = registry.get("memory_get")

    assert memory_search is not None
    assert memory_get is not None
    assert "MEMORY.md + memory/**/*.md" in memory_search.spec.description
    assert "MEMORY.md or memory/**/*.md" in memory_get.spec.description
    assert "MEMORY.md or memory/**/*.md" in memory_get.spec.parameters["path"][
        "description"
    ]
