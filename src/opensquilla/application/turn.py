"""Application-layer turn orchestration contracts.

This module is the first landing zone for extracting ``engine.runtime`` into
small use-case services. It defines the application-facing composition points
without changing the current runtime path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from opensquilla.contracts import (
    EventPublisherPort,
    ProviderMessage,
    ToolContext,
    ToolSpec,
    TurnEvent,
)


@dataclass(frozen=True)
class TurnRequest:
    session_key: str
    message: str
    agent_id: str = "main"
    attachments: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    messages: tuple[ProviderMessage, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptAssemblerPort(Protocol):
    async def assemble(self, request: TurnRequest) -> PromptBundle: ...


class ToolSurfaceBuilderPort(Protocol):
    async def build(self, request: TurnRequest, context: ToolContext) -> list[ToolSpec]: ...


class HistoryServicePort(Protocol):
    async def load_messages(self, request: TurnRequest) -> list[ProviderMessage]: ...

    async def persist_event(self, request: TurnRequest, event: TurnEvent) -> None: ...


class MemoryOrchestratorPort(Protocol):
    async def enrich(
        self,
        request: TurnRequest,
        messages: list[ProviderMessage],
    ) -> list[ProviderMessage]: ...


class ProviderExecutorPort(Protocol):
    def execute(
        self,
        request: TurnRequest,
        prompt: PromptBundle,
        tools: list[ToolSpec],
    ) -> AsyncIterator[TurnEvent]: ...


@dataclass(frozen=True)
class TurnUseCase:
    """Thin coordinator for the future extracted turn runtime."""

    prompt_assembler: PromptAssemblerPort
    tool_surface_builder: ToolSurfaceBuilderPort
    history_service: HistoryServicePort
    memory_orchestrator: MemoryOrchestratorPort
    provider_executor: ProviderExecutorPort
    event_publisher: EventPublisherPort | None = None

    async def run(self, request: TurnRequest, context: ToolContext) -> AsyncIterator[TurnEvent]:
        history = await self.history_service.load_messages(request)
        enriched = await self.memory_orchestrator.enrich(request, history)
        prompt = await self.prompt_assembler.assemble(
            TurnRequest(
                session_key=request.session_key,
                message=request.message,
                agent_id=request.agent_id,
                attachments=request.attachments,
                metadata={**request.metadata, "history": enriched},
            )
        )
        tools = await self.tool_surface_builder.build(request, context)
        async for event in self.provider_executor.execute(request, prompt, tools):
            await self.history_service.persist_event(request, event)
            if self.event_publisher is not None:
                await self.event_publisher.publish(event)
            yield event


__all__ = [
    "HistoryServicePort",
    "MemoryOrchestratorPort",
    "PromptAssemblerPort",
    "PromptBundle",
    "ProviderExecutorPort",
    "ToolSurfaceBuilderPort",
    "TurnRequest",
    "TurnUseCase",
]
