from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from opensquilla.application import PromptBundle, TurnRequest, TurnUseCase
from opensquilla.contracts import ProviderMessage, TextDelta, ToolContext, TurnEvent


@dataclass
class _FakeHistory:
    persisted: list[TurnEvent] = field(default_factory=list)

    async def load_messages(self, request: TurnRequest) -> list[ProviderMessage]:
        return [ProviderMessage(role="user", content=f"history:{request.session_key}")]

    async def persist_event(self, request: TurnRequest, event: TurnEvent) -> None:
        self.persisted.append(event)


class _FakeMemory:
    async def enrich(
        self,
        request: TurnRequest,
        messages: list[ProviderMessage],
    ) -> list[ProviderMessage]:
        return [*messages, ProviderMessage(role="system", content="memory")]


@dataclass
class _FakePrompt:
    seen_history_size: int = 0

    async def assemble(self, request: TurnRequest) -> PromptBundle:
        self.seen_history_size = len(request.metadata["history"])
        return PromptBundle(system_prompt="system", messages=())


class _FakeTools:
    async def build(self, request: TurnRequest, context: ToolContext) -> list:
        return []


class _FakeProvider:
    def execute(
        self,
        request: TurnRequest,
        prompt: PromptBundle,
        tools: list,
    ) -> AsyncIterator[TurnEvent]:
        async def _events() -> AsyncIterator[TurnEvent]:
            yield TextDelta(text=prompt.system_prompt)

        return _events()


@dataclass
class _FakePublisher:
    published: list[TurnEvent] = field(default_factory=list)

    async def publish(self, event: TurnEvent) -> None:
        self.published.append(event)


@pytest.mark.asyncio
async def test_turn_use_case_coordinates_services_in_order() -> None:
    history = _FakeHistory()
    prompt = _FakePrompt()
    publisher = _FakePublisher()
    use_case = TurnUseCase(
        prompt_assembler=prompt,
        tool_surface_builder=_FakeTools(),
        history_service=history,
        memory_orchestrator=_FakeMemory(),
        provider_executor=_FakeProvider(),
        event_publisher=publisher,
    )

    events = [
        event
        async for event in use_case.run(
            TurnRequest(session_key="s1", message="hello"),
            ToolContext(is_owner=True),
        )
    ]

    assert events == [TextDelta(text="system")]
    assert history.persisted == events
    assert publisher.published == events
    assert prompt.seen_history_size == 2
