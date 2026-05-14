from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from opensquilla.engine.runtime import TurnRunner
from opensquilla.engine.types import AgentConfig, DoneEvent
from opensquilla.gateway.config import GatewayConfig


class _SessionConfigManager:
    def __init__(self, config: object | None) -> None:
        self.config = config

    def get_session_config(self, session_key: str) -> object | None:
        return self.config


def test_resolve_agent_iteration_timeout_prefers_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", "222")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_iteration_timeout_seconds=111.0)
        ),
        config=GatewayConfig(agent_iteration_timeout_seconds=333.0),
    )

    assert runner._resolve_agent_iteration_timeout("agent:main:test", 444.0) == 444.0


def test_resolve_agent_iteration_timeout_prefers_session_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", "222")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_iteration_timeout_seconds=111.0)
        ),
        config=GatewayConfig(agent_iteration_timeout_seconds=333.0),
    )

    assert runner._resolve_agent_iteration_timeout("agent:main:test") == 111.0


def test_resolve_agent_iteration_timeout_prefers_env_over_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", "222")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_iteration_timeout_seconds=333.0),
    )

    assert runner._resolve_agent_iteration_timeout("agent:main:test") == 222.0


def test_resolve_agent_iteration_timeout_uses_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", raising=False)
    runner = TurnRunner(
        provider_selector=None,
        config=GatewayConfig(agent_iteration_timeout_seconds=333.0),
    )

    assert runner._resolve_agent_iteration_timeout("agent:main:test") == 333.0


def test_resolve_agent_iteration_timeout_uses_agent_default_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", raising=False)
    runner = TurnRunner(provider_selector=None, config=None)

    assert (
        runner._resolve_agent_iteration_timeout("agent:main:test")
        == AgentConfig().iteration_timeout
    )


def test_resolve_agent_iteration_timeout_invalid_env_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_ITERATION_TIMEOUT", "not-a-float")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_iteration_timeout_seconds=333.0),
    )

    assert runner._resolve_agent_iteration_timeout("agent:main:test") == 333.0


def test_resolve_agent_iteration_timeout_rejects_invalid_explicit_value() -> None:
    runner = TurnRunner(provider_selector=None, config=GatewayConfig())

    with pytest.raises(ValueError, match="iteration_timeout"):
        runner._resolve_agent_iteration_timeout("agent:main:test", -1.0)


@pytest.mark.asyncio
async def test_run_threads_iteration_timeout_into_agent_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: runner.run(iteration_timeout=X) must reach AgentConfig.

    iteration_timeout was previously declared on TurnRunner.run() and
    referenced inside _run_turn() at the resolver call site, but never
    plumbed through _run_turn()'s signature or the two run() -> _run_turn()
    call sites. Every turn would hit NameError before reaching the resolver.
    The existing isolation tests above exercise the resolver directly and
    so would not have caught the threading gap.
    """
    from opensquilla.tools.types import ToolContext

    seen_kwargs: list[dict[str, Any]] = []
    real_agent_config = AgentConfig

    def recording_agent_config(**kwargs: Any) -> AgentConfig:
        seen_kwargs.append(kwargs)
        return real_agent_config(**kwargs)

    monkeypatch.setattr(
        "opensquilla.engine.runtime.AgentConfig", recording_agent_config
    )

    provider = MagicMock()
    provider.provider_name = "stub"

    async def _chat(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        yield DoneEvent()

    provider.chat = _chat

    selector = MagicMock()
    selector.resolve.return_value = provider
    selector.clone.return_value = selector
    selector.current_config = MagicMock(model="stub-model")

    session_manager = MagicMock()
    session_manager.get = AsyncMock(return_value=None)
    session_manager.append_message = AsyncMock(return_value=None)
    session_manager.update = AsyncMock(return_value=None)
    session_manager.get_compaction_summary = AsyncMock(return_value=None)

    runner = TurnRunner(
        provider_selector=selector,
        session_manager=session_manager,
    )

    tool_ctx = ToolContext(session_key="agent:main:iter-thread-test")

    async for _ in runner.run(
        message="hi",
        session_key="agent:main:iter-thread-test",
        tool_context=tool_ctx,
        iteration_timeout=444.0,
    ):
        pass

    assert any(kw.get("iteration_timeout") == 444.0 for kw in seen_kwargs), (
        f"AgentConfig never received iteration_timeout=444.0; saw {seen_kwargs!r}"
    )
