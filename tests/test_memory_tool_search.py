from __future__ import annotations

import pytest

from opensquilla.memory.runtime import reset_memory_tools_runtime
from opensquilla.memory.tool_search import (
    bounded_memory_search_evidence,
    clean_memory_search_evidence,
    format_memory_search_results,
    memory_search_limit,
    search_memory_tool,
)
from opensquilla.memory.types import (
    MemorySearchOpts,
    MemorySearchResult,
    MemorySource,
    SearchIntent,
)
from opensquilla.tools.builtin.memory_tools import create_memory_tools
from opensquilla.tools.registry import ToolRegistry


class FakeRetriever:
    def __init__(self, results: list[MemorySearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, MemorySearchOpts, SearchIntent]] = []

    async def search(
        self,
        query: str,
        opts: MemorySearchOpts,
        *,
        intent: SearchIntent,
    ) -> list[MemorySearchResult]:
        self.calls.append((query, opts, intent))
        return self.results


@pytest.fixture(autouse=True)
def reset_runtime():
    reset_memory_tools_runtime()
    yield
    reset_memory_tools_runtime()


def _result(
    *,
    path: str = "memory/note.md",
    start_line: int = 4,
    end_line: int = 6,
    snippet: str = "snippet body",
    text: str | None = None,
    score: float = 0.4567,
    text_score: float | None = 0.12,
    citation: str | None = None,
) -> MemorySearchResult:
    return MemorySearchResult(
        chunk_id="chunk-1",
        path=path,
        source=MemorySource.memory,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
        score=score,
        text_score=text_score,
        text=text,
        citation=citation,
    )


def test_memory_search_limit_clamps_supported_inputs() -> None:
    assert memory_search_limit(5) == 5
    assert memory_search_limit("7") == 7
    assert memory_search_limit(0) == 1
    assert memory_search_limit(100) == 20
    assert memory_search_limit("not-an-int") == 10
    assert memory_search_limit(object()) == 10


def test_clean_memory_search_evidence_removes_frontmatter_and_leading_headings() -> None:
    text = "---\ntitle: Demo\n---\n# Note title\n\nRelevant decision\n"

    assert clean_memory_search_evidence(text) == "Relevant decision"


def test_bounded_memory_search_evidence_centers_query_match() -> None:
    lines = [f"preamble {i} " + ("a" * 90) for i in range(18)]
    lines.append("needle decision " + ("b" * 60))
    lines.extend(f"tail {i} " + ("c" * 90) for i in range(18))

    evidence = bounded_memory_search_evidence("\n".join(lines), query="needle decision")

    assert "needle decision" in evidence
    assert "preamble 0" not in evidence
    assert len(evidence) <= 900


def test_format_memory_search_results_includes_citation_scores_and_cleaned_evidence() -> None:
    result = _result(text="---\ntitle: Demo\n---\n# Memory title\n\nBody line")

    formatted = format_memory_search_results([result], query="body")

    assert (
        "[1] memory/note.md (lines 4-6; citation: memory/note.md#L4-L6; "
        "score: 0.457, text_score: 0.120)"
    ) in formatted
    assert "Body line" in formatted
    assert "Memory title" not in formatted


@pytest.mark.asyncio
async def test_search_memory_tool_uses_tool_intent_and_formats_empty_results() -> None:
    retriever = FakeRetriever([])

    result = await search_memory_tool(retriever, "alpha", "99")

    assert result == "No results found."
    assert retriever.calls[0][0] == "alpha"
    assert retriever.calls[0][1].max_results == 20
    assert retriever.calls[0][2] is SearchIntent.TOOL


@pytest.mark.asyncio
async def test_registered_memory_search_delegates_to_memory_boundary() -> None:
    retriever = FakeRetriever([_result(snippet="alpha body", citation="memory/note.md#L4-L6")])
    registry = ToolRegistry()
    create_memory_tools(object(), retriever, registry=registry, memory_source="workspace")
    tool = registry.get("memory_search")
    assert tool is not None

    result = await tool.handler(query="alpha", max_results=3)

    assert "alpha body" in result
    assert "citation: memory/note.md#L4-L6" in result
    assert retriever.calls[0][1].max_results == 3
    assert retriever.calls[0][2] is SearchIntent.TOOL
