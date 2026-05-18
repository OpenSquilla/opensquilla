from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from opensquilla.engine import Agent, AgentConfig
from opensquilla.engine.runtime import TurnRunner, _prepend_request_context_prompt
from opensquilla.provider import ChatConfig, DoneEvent, Message, TextDeltaEvent
from opensquilla.session.manager import SessionManager
from opensquilla.session.models import SessionSummary
from opensquilla.session.storage import SessionStorage


class _CapturingProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        config: ChatConfig | None = None,
    ) -> AsyncIterator[Any]:
        self.calls.append({"messages": messages, "tools": tools, "config": config})
        return self._stream()

    async def _stream(self) -> AsyncIterator[Any]:
        yield TextDeltaEvent(text="ok")
        yield DoneEvent(stop_reason="end_turn", input_tokens=3, output_tokens=1)

    async def list_models(self) -> list[Any]:
        return []


@pytest.fixture
async def session_manager() -> AsyncIterator[SessionManager]:
    storage = SessionStorage(":memory:")
    await storage.connect()
    manager = SessionManager(storage, inject_time_prefix=False)
    yield manager
    await storage.close()


@pytest.mark.asyncio
async def test_load_history_skips_legacy_summary_marker_and_returns_dynamic_context(
    session_manager: SessionManager,
) -> None:
    key = "agent:main:stable"
    node = await session_manager.create(key)
    await session_manager.append_message(key, "system", "[Context Summary]\nlegacy summary")
    await session_manager.append_message(key, "user", "old question")
    await session_manager.append_message(key, "assistant", "old answer")
    await session_manager._storage.save_summary(
        SessionSummary(
            session_id=node.session_id,
            session_key=key,
            summary_text="stored durable summary",
        )
    )

    runner = TurnRunner(provider_selector=MagicMock(), session_manager=session_manager)
    agent = Agent(provider=_CapturingProvider(), config=AgentConfig(system_prompt="stable base"))

    summary_context = await runner._load_history(agent, key, trim_last_user=False)

    assert summary_context is not None
    assert "[Compacted Session Summaries]" in summary_context
    assert "stored durable summary" in summary_context
    assert "legacy summary" in summary_context
    assert [message.content for message in agent._history] == ["old question", "old answer"]
    assert agent.config.system_prompt == "stable base"


@pytest.mark.asyncio
async def test_summary_context_is_request_only_and_keeps_system_cache_anchor(
    session_manager: SessionManager,
) -> None:
    key = "agent:main:stable"
    node = await session_manager.create(key)
    await session_manager.append_message(key, "user", "old question")
    await session_manager.append_message(key, "assistant", "old answer")
    await session_manager._storage.save_summary(
        SessionSummary(
            session_id=node.session_id,
            session_key=key,
            summary_text="summary outside transcript",
        )
    )
    provider = _CapturingProvider()
    agent = Agent(
        provider=provider,
        config=AgentConfig(
            system_prompt="stable base",
            request_context_prompt="<memory_context>volatile recall</memory_context>",
            cache_breakpoints=[{"text": "stable base", "cache": "true"}],
            cache_mode="auto",
            max_iterations=1,
        ),
        session_key=key,
    )
    runner = TurnRunner(provider_selector=MagicMock(), session_manager=session_manager)

    summary_context = await runner._load_history(agent, key, trim_last_user=False)
    agent.config.request_context_prompt = _prepend_request_context_prompt(
        agent.config.request_context_prompt,
        summary_context,
    )
    events = [event async for event in agent.run_turn("current question")]

    assert any(event.kind == "done" for event in events)
    call = provider.calls[0]
    assert call["config"].system == "stable base"
    assert call["config"].cache_breakpoints == [{"text": "stable base", "cache": "true"}]
    request_context = call["messages"][0].content
    assert "[Request context for this turn]" in request_context
    assert [message.content for message in call["messages"][1:3]] == [
        "old question",
        "old answer",
    ]
    assert "[Compacted Session Summaries]" in request_context
    assert "summary outside transcript" in request_context
    assert "<memory_context>volatile recall</memory_context>" in request_context
    assert call["messages"][-1].role == "user"
    assert call["messages"][-1].content.startswith("current question")
    assert "[Runtime context for this turn]" in call["messages"][-1].content
    assert all(
        "summary outside transcript" not in message.content
        for message in agent._history
        if isinstance(message.content, str)
    )
