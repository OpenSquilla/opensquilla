from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from opensquilla.application.backplane import ContractBackplane
from opensquilla.contracts import (
    ChannelIngressPort,
    IncomingMessage,
    MemoryQuery,
    MemoryResult,
    ProviderChatOptions,
    ProviderMessage,
    ProviderModelInfo,
    ProviderPort,
    SessionRecord,
    SessionStatus,
    ToolContext,
    ToolHandler,
    ToolSpec,
    TurnEvent,
)


@dataclass
class _FakeToolRegistry:
    specs: list[ToolSpec]

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self.specs.append(spec)

    def get(self, name: str) -> tuple[ToolSpec, ToolHandler] | None:
        for spec in self.specs:
            if spec.name == name:
                async def _handler(_call: Any, _context: ToolContext) -> Any:
                    return None

                return spec, _handler
        return None

    def list_specs(self, context: ToolContext | None = None) -> list[ToolSpec]:
        return list(self.specs)


class _FakeToolPolicy:
    def filter_tools(self, specs: list[ToolSpec], context: ToolContext) -> list[ToolSpec]:
        return [spec for spec in specs if spec.name not in context.denied_tools]


@dataclass
class _FakeSessionStore:
    seen: list[str] = field(default_factory=list)

    async def get_session(self, session_key: str) -> SessionRecord | None:
        self.seen.append(session_key)
        return SessionRecord(
            session_key=session_key,
            session_id="sid",
            status=SessionStatus.RUNNING,
        )

    async def create_session(self, session: SessionRecord) -> SessionRecord:
        return session

    async def update_session_status(self, session_key: str, status: SessionStatus) -> None:
        self.seen.append(f"{session_key}:{status}")

    async def append_transcript(self, entry: Any) -> None:
        return None

    async def list_transcript(self, session_id: str, limit: int | None = None) -> list[Any]:
        return []


@dataclass
class _FakeMemory:
    queries: list[MemoryQuery] = field(default_factory=list)

    async def search(self, query: MemoryQuery) -> list[MemoryResult]:
        self.queries.append(query)
        return [MemoryResult(id="m1", text=query.text, score=0.9, source=query.agent_id)]

    async def save(
        self,
        *,
        agent_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return f"{agent_id}:{text}"


class _FakeProvider(ProviderPort):
    provider_name = "fake"

    def chat(
        self,
        messages: list[ProviderMessage],
        tools: list[Any] | None = None,
        options: ProviderChatOptions | None = None,
    ) -> AsyncIterator[TurnEvent]:
        async def _empty() -> AsyncIterator[TurnEvent]:
            if False:
                yield None  # pragma: no cover

        return _empty()

    async def list_models(self) -> list[ProviderModelInfo]:
        return [ProviderModelInfo(id="fake-model")]


@dataclass
class _FakeProviderFactory:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def build_provider(self, provider_id: str, config: dict[str, Any]) -> ProviderPort:
        self.calls.append((provider_id, config))
        return _FakeProvider()


@dataclass
class _FakeChannelIngress(ChannelIngressPort):
    handled: list[tuple[str, IncomingMessage]] = field(default_factory=list)

    async def handle_incoming(self, channel_name: str, message: IncomingMessage) -> None:
        self.handled.append((channel_name, message))


@pytest.mark.asyncio
async def test_contract_backplane_routes_subsystem_calls_through_ports() -> None:
    registry = _FakeToolRegistry(
        [
            ToolSpec(name="read_file", description="read"),
            ToolSpec(name="write_file", description="write"),
        ]
    )
    session_store = _FakeSessionStore()
    memory = _FakeMemory()
    provider_factory = _FakeProviderFactory()
    channel_ingress = _FakeChannelIngress()
    backplane = ContractBackplane(
        tool_registry=registry,
        tool_policy=_FakeToolPolicy(),
        session_store=session_store,
        provider_factory=provider_factory,
        channel_ingress=channel_ingress,
        memory=memory,
    )

    visible_tools = backplane.list_tool_specs(ToolContext(denied_tools=frozenset({"write_file"})))
    session = await backplane.get_session("s1")
    memory_results = await backplane.search_memory("needle", agent_id="agent-a", limit=2)
    provider = backplane.build_provider("fake", {"model": "fake-model"})
    await backplane.handle_channel_message(
        "telegram",
        IncomingMessage(sender_id="u1", channel_id="c1", content="hello"),
    )

    assert [spec.name for spec in visible_tools] == ["read_file"]
    assert session == SessionRecord(
        session_key="s1",
        session_id="sid",
        status=SessionStatus.RUNNING,
    )
    assert memory.queries == [MemoryQuery(text="needle", agent_id="agent-a", limit=2)]
    assert memory_results == [MemoryResult(id="m1", text="needle", score=0.9, source="agent-a")]
    assert provider.provider_name == "fake"
    assert provider_factory.calls == [("fake", {"model": "fake-model"})]
    assert channel_ingress.handled == [
        ("telegram", IncomingMessage(sender_id="u1", channel_id="c1", content="hello"))
    ]


def test_contract_backplane_is_safe_when_optional_ports_are_absent() -> None:
    backplane = ContractBackplane()

    assert backplane.list_tool_specs(ToolContext()) == []
    assert backplane.build_provider("missing", {}) is None


def test_contract_backplane_reports_missing_required_ports_for_runtime_assembly() -> None:
    registry = _FakeToolRegistry([ToolSpec(name="read_file", description="read")])
    backplane = ContractBackplane(tool_registry=registry)

    assert backplane.missing_ports("tool_registry", "provider_factory", "memory") == (
        "provider_factory",
        "memory",
    )
    assert backplane.require_ports("tool_registry") is backplane

    with pytest.raises(
        ValueError,
        match="ContractBackplane missing required ports: provider_factory, memory",
    ):
        backplane.require_ports("provider_factory", "memory")
