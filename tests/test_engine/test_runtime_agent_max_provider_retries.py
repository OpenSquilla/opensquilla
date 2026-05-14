from __future__ import annotations

from types import SimpleNamespace

import pytest

from opensquilla.engine.runtime import TurnRunner
from opensquilla.engine.types import AgentConfig
from opensquilla.gateway.config import GatewayConfig


class _SessionConfigManager:
    def __init__(self, config: object | None) -> None:
        self.config = config

    def get_session_config(self, session_key: str) -> object | None:
        return self.config


def test_resolve_agent_max_provider_retries_prefers_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", "2")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_max_provider_retries=1)
        ),
        config=GatewayConfig(agent_max_provider_retries=3),
    )

    assert runner._resolve_agent_max_provider_retries("agent:main:test", 4) == 4


def test_resolve_agent_max_provider_retries_prefers_session_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", "2")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_max_provider_retries=1)
        ),
        config=GatewayConfig(agent_max_provider_retries=3),
    )

    assert runner._resolve_agent_max_provider_retries("agent:main:test") == 1


def test_resolve_agent_max_provider_retries_prefers_env_over_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", "2")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_max_provider_retries=3),
    )

    assert runner._resolve_agent_max_provider_retries("agent:main:test") == 2


def test_resolve_agent_max_provider_retries_uses_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", raising=False)
    runner = TurnRunner(
        provider_selector=None,
        config=GatewayConfig(agent_max_provider_retries=3),
    )

    assert runner._resolve_agent_max_provider_retries("agent:main:test") == 3


def test_resolve_agent_max_provider_retries_uses_agent_default_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", raising=False)
    runner = TurnRunner(provider_selector=None, config=None)

    assert (
        runner._resolve_agent_max_provider_retries("agent:main:test")
        == AgentConfig().max_provider_retries
    )


def test_resolve_agent_max_provider_retries_invalid_env_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", "not-an-int")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_max_provider_retries=3),
    )

    assert runner._resolve_agent_max_provider_retries("agent:main:test") == 3


def test_resolve_agent_max_provider_retries_accepts_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_MAX_PROVIDER_RETRIES", raising=False)
    runner = TurnRunner(provider_selector=None, config=GatewayConfig())

    assert runner._resolve_agent_max_provider_retries("agent:main:test", 0) == 0


def test_resolve_agent_max_provider_retries_rejects_invalid_explicit_value() -> None:
    runner = TurnRunner(provider_selector=None, config=GatewayConfig())

    with pytest.raises(ValueError, match="max_provider_retries"):
        runner._resolve_agent_max_provider_retries("agent:main:test", -1)
