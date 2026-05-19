from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.gateway.auth import Principal
from opensquilla.gateway.config import GatewayConfig
from opensquilla.gateway.rpc import RpcContext, get_dispatcher
from opensquilla.gateway.scopes import METHOD_SCOPES, READ_SCOPE, WRITE_SCOPE
from opensquilla.memory.types import MemorySearchResult, MemorySource, SearchIntent
from opensquilla.search.registry import register_provider
from opensquilla.search.types import SearchProviderError, SearchProviderSpec, SearchResult
from opensquilla.tools.builtin.web import configure_search, run_web_search_payload


@dataclass
class FakeMemoryManager:
    workspace_dir: Any
    memory_config: Any = field(
        default_factory=lambda: SimpleNamespace(index_captured_turns=False)
    )
    search_calls: list[tuple[str, Any, Any]] | None = None

    async def search(self, query: str, opts: Any, *, intent: Any) -> list[MemorySearchResult]:
        if self.search_calls is None:
            self.search_calls = []
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


def _ctx(**kwargs: Any) -> RpcContext:
    defaults: dict[str, Any] = {"conn_id": "test", "config": GatewayConfig()}
    defaults.update(kwargs)
    return RpcContext(**defaults)


class FakeProviderSelector:
    current_config = SimpleNamespace(provider="openrouter")

    async def list_models(self) -> list[dict[str, object]]:
        return [
            {"provider": "openrouter", "model_id": "openrouter/a"},
            {"provider": "ollama", "model_id": "local/b"},
        ]


@pytest.fixture(autouse=True)
def _reset_search_config():
    configure_search("duckduckgo", max_results=5)
    yield
    configure_search("duckduckgo", max_results=5)


@pytest.mark.asyncio
async def test_new_product_rpc_methods_are_classified_read_scope():
    dispatcher = get_dispatcher()
    for method in (
        "memory.list",
        "memory.search",
        "memory.show",
        "providers.status",
        "search.status",
    ):
        assert METHOD_SCOPES[method] == READ_SCOPE
        entry = dispatcher.get_entry(method)
        assert entry is not None
        assert entry.required_scope == READ_SCOPE


@pytest.mark.asyncio
async def test_search_query_is_classified_write_scope_and_denies_read_only():
    dispatcher = get_dispatcher()
    entry = dispatcher.get_entry("search.query")
    assert METHOD_SCOPES["search.query"] == WRITE_SCOPE
    assert entry is not None
    assert entry.required_scope == WRITE_SCOPE

    read_only = Principal(
        role="operator",
        scopes=frozenset({READ_SCOPE}),
        is_owner=False,
        authenticated=True,
    )
    res = await dispatcher.dispatch(
        "r1",
        "search.query",
        {"query": "hello"},
        _ctx(principal=read_only),
    )

    assert res.error is not None
    assert res.error.code == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_memory_search_uses_admin_intent_and_returns_wire_rows(tmp_path):
    manager = FakeMemoryManager(workspace_dir=tmp_path)
    res = await get_dispatcher().dispatch(
        "r1",
        "memory.search",
        {"query": "alpha", "agentId": "main", "limit": 3},
        _ctx(memory_managers={"main": manager}),
    )

    assert res.error is None, res.error
    assert res.payload["count"] == 1
    assert res.payload["results"][0]["chunkId"] == "chunk-1"
    assert manager.search_calls is not None
    assert manager.search_calls[0][2] is SearchIntent.ADMIN
    assert manager.search_calls[0][1].max_results == 3


@pytest.mark.asyncio
async def test_memory_search_reports_unavailable_and_missing_agent(tmp_path):
    unavailable = await get_dispatcher().dispatch(
        "r1",
        "memory.search",
        {"query": "alpha"},
        _ctx(),
    )
    missing = await get_dispatcher().dispatch(
        "r2",
        "memory.search",
        {"query": "alpha", "agentId": "ops"},
        _ctx(memory_managers={"main": FakeMemoryManager(workspace_dir=tmp_path)}),
    )

    assert unavailable.error is not None
    assert unavailable.error.code == "UNAVAILABLE"
    assert missing.error is not None
    assert missing.error.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_memory_list_returns_public_source_files_only(tmp_path):
    (tmp_path / "MEMORY.md").write_text("root\n", encoding="utf-8")
    memory_dir = tmp_path / "memory"
    archive_dir = memory_dir / "archive"
    hidden_dir = memory_dir / ".private"
    archive_dir.mkdir(parents=True)
    hidden_dir.mkdir(parents=True)
    (memory_dir / "a.md").write_text("one\ntwo\n", encoding="utf-8")
    (archive_dir / "x.md").write_text("private\n", encoding="utf-8")
    (hidden_dir / "x.md").write_text("hidden\n", encoding="utf-8")

    res = await get_dispatcher().dispatch(
        "r1",
        "memory.list",
        {"agentId": "main"},
        _ctx(memory_managers={"main": FakeMemoryManager(workspace_dir=tmp_path)}),
    )

    assert res.error is None, res.error
    paths = [row["path"] for row in res.payload["files"]]
    assert paths == ["MEMORY.md", "memory/a.md"]
    assert res.payload["files"][1]["lineCount"] == 2


@pytest.mark.asyncio
async def test_memory_show_line_slice_and_truncation(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "a.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (memory_dir / "long.md").write_text("x" * 9001, encoding="utf-8")
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    sliced = await get_dispatcher().dispatch(
        "r1",
        "memory.show",
        {"path": "memory/a.md", "fromLine": 2, "lines": 1},
        _ctx(memory_managers={"main": manager}),
    )
    truncated = await get_dispatcher().dispatch(
        "r2",
        "memory.show",
        {"path": "memory/long.md"},
        _ctx(memory_managers={"main": manager}),
    )

    assert sliced.error is None, sliced.error
    assert sliced.payload["content"] == "two"
    assert sliced.payload["fromLine"] == 2
    assert sliced.payload["lineCount"] == 1
    assert truncated.error is None, truncated.error
    assert truncated.payload["truncated"] is True
    assert len(truncated.payload["content"]) == 8000


@pytest.mark.asyncio
async def test_memory_show_rejects_traversal_archive_excess_lines_and_big_unsliced_file(tmp_path):
    memory_dir = tmp_path / "memory"
    archive_dir = memory_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "x.md").write_text("private", encoding="utf-8")
    big = memory_dir / "big.md"
    big.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    manager = FakeMemoryManager(workspace_dir=tmp_path)

    traversal = await get_dispatcher().dispatch(
        "r1",
        "memory.show",
        {"path": "../secret.md"},
        _ctx(memory_managers={"main": manager}),
    )
    archive = await get_dispatcher().dispatch(
        "r2",
        "memory.show",
        {"path": "memory/archive/x.md"},
        _ctx(memory_managers={"main": manager}),
    )
    too_many_lines = await get_dispatcher().dispatch(
        "r3",
        "memory.show",
        {"path": "memory/big.md", "lines": 501},
        _ctx(memory_managers={"main": manager}),
    )
    sliced_big = await get_dispatcher().dispatch(
        "r4",
        "memory.show",
        {"path": "memory/big.md", "lines": 1},
        _ctx(memory_managers={"main": manager}),
    )
    too_big = await get_dispatcher().dispatch(
        "r5",
        "memory.show",
        {"path": "memory/big.md"},
        _ctx(memory_managers={"main": manager}),
    )

    assert traversal.error is not None
    assert traversal.error.code == "INVALID_REQUEST"
    assert archive.error is not None
    assert archive.error.code == "INVALID_REQUEST"
    assert too_many_lines.error is not None
    assert too_many_lines.error.code == "INVALID_REQUEST"
    assert sliced_big.error is None, sliced_big.error
    assert sliced_big.payload["lineCount"] == 1
    assert sliced_big.payload["truncated"] is True
    assert too_big.error is not None
    assert too_big.error.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_providers_status_redacts_keys_and_rejects_unknown_provider():
    cfg = GatewayConfig(
        llm={
            "provider": "openrouter",
            "model": "openrouter/model",
            "api_key": "secret-key",
        }
    )
    ok = await get_dispatcher().dispatch(
        "r1",
        "providers.status",
        {"provider": "openrouter"},
        _ctx(config=cfg),
    )
    unknown = await get_dispatcher().dispatch(
        "r2",
        "providers.status",
        {"provider": "definitely_missing"},
        _ctx(config=cfg),
    )

    assert ok.error is None, ok.error
    rendered = repr(ok.payload)
    assert "secret-key" not in rendered
    assert ok.payload["providers"][0]["apiKeyConfigured"] is True
    assert unknown.error is not None
    assert unknown.error.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_providers_status_probe_models_returns_wire_shape():
    cfg = GatewayConfig(
        llm={
            "provider": "openrouter",
            "model": "openrouter/model",
            "api_key": "secret-key",
        }
    )
    res = await get_dispatcher().dispatch(
        "r1",
        "providers.status",
        {"provider": "openrouter", "probeModels": True},
        _ctx(config=cfg, provider_selector=FakeProviderSelector()),
    )

    assert res.error is None, res.error
    row = res.payload["providers"][0]
    assert row["active"] is True
    assert row["modelProbe"] == {
        "attempted": True,
        "status": "ok",
        "count": 1,
        "error": None,
    }


class FakeSearchProvider:
    name = "fake_search_ok"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return [SearchResult(title="Title", url="https://example.com", snippet=query)]


class FailingSearchProvider:
    name = "fake_search_fail"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise SearchProviderError(
            provider=self.name,
            kind="network",
            message="network down",
            retryable=True,
        )


@pytest.mark.asyncio
async def test_search_status_and_query_return_structured_payloads():
    register_provider(
        "fake_search_ok",
        FakeSearchProvider,
        SearchProviderSpec(provider_id="fake_search_ok"),
    )
    configure_search("fake_search_ok", max_results=4, diagnostics=True)

    status = await get_dispatcher().dispatch("r1", "search.status", {}, _ctx())
    query = await get_dispatcher().dispatch(
        "r2",
        "search.query",
        {"query": "hello", "limit": 2},
        _ctx(),
    )

    assert status.error is None, status.error
    assert status.payload["provider"] == "fake_search_ok"
    assert status.payload["apiKeyConfigured"] is False
    assert query.error is None, query.error
    assert query.payload["ok"] is True
    assert query.payload["results"][0]["snippet"] == "hello"


@pytest.mark.asyncio
async def test_search_query_provider_failure_is_ok_false_payload():
    register_provider(
        "fake_search_fail",
        FailingSearchProvider,
        SearchProviderSpec(provider_id="fake_search_fail"),
    )
    configure_search("fake_search_fail", diagnostics=True)

    res = await get_dispatcher().dispatch(
        "r1",
        "search.query",
        {"query": "hello"},
        _ctx(),
    )

    assert res.error is None, res.error
    assert res.payload["ok"] is False
    assert res.payload["error"]["kind"] == "network"
    assert res.payload["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_search_sensitive_query_is_not_echoed_by_tool_or_rpc():
    secret_query = "API_KEY=super-secret-value"
    helper_payload = await run_web_search_payload(secret_query)
    rpc_res = await get_dispatcher().dispatch(
        "r1",
        "search.query",
        {"query": secret_query},
        _ctx(),
    )

    assert "super-secret-value" not in repr(helper_payload)
    assert "API_KEY" not in repr(helper_payload)
    assert "sensitive" in repr(helper_payload).lower()
    assert helper_payload["query"] == "[redacted]"
    assert rpc_res.error is None, rpc_res.error
    assert repr(rpc_res.payload).find("super-secret-value") == -1
    assert repr(rpc_res.payload).find("API_KEY") == -1
    assert rpc_res.payload["query"] == "[redacted]"
    assert rpc_res.payload["ok"] is False
