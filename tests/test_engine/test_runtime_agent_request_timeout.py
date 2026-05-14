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


def test_resolve_agent_request_timeout_prefers_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", "22")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_request_timeout_seconds=11.0)
        ),
        config=GatewayConfig(agent_request_timeout_seconds=33.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test", 44.0) == 44.0


def test_resolve_agent_request_timeout_prefers_session_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", "22")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(
            SimpleNamespace(agent_request_timeout_seconds=11.0)
        ),
        config=GatewayConfig(agent_request_timeout_seconds=33.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test") == 11.0


def test_resolve_agent_request_timeout_prefers_env_over_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", "22")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_request_timeout_seconds=33.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test") == 22.0


def test_resolve_agent_request_timeout_uses_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", raising=False)
    runner = TurnRunner(
        provider_selector=None,
        config=GatewayConfig(agent_request_timeout_seconds=33.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test") == 33.0


def test_resolve_agent_request_timeout_falls_back_to_llm_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the new agent_request_timeout_seconds is unset, the legacy
    llm_request_timeout_seconds must still apply so existing deployments
    keep their tuned value. This is the regression-prevention test for
    operators who set llm_request_timeout_seconds before the new knob
    existed.
    """
    monkeypatch.delenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", raising=False)
    runner = TurnRunner(
        provider_selector=None,
        config=GatewayConfig(llm_request_timeout_seconds=77.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test") == 77.0


def test_resolve_agent_request_timeout_uses_agent_default_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", raising=False)
    runner = TurnRunner(provider_selector=None, config=None)

    assert (
        runner._resolve_agent_request_timeout("agent:main:test")
        == AgentConfig().request_timeout
    )


def test_resolve_agent_request_timeout_invalid_env_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSQUILLA_AGENT_REQUEST_TIMEOUT", "not-a-float")
    runner = TurnRunner(
        provider_selector=None,
        session_manager=_SessionConfigManager(None),
        config=GatewayConfig(agent_request_timeout_seconds=33.0),
    )

    assert runner._resolve_agent_request_timeout("agent:main:test") == 33.0


def test_resolve_agent_request_timeout_rejects_invalid_explicit_value() -> None:
    runner = TurnRunner(provider_selector=None, config=GatewayConfig())

    with pytest.raises(ValueError, match="request_timeout"):
        runner._resolve_agent_request_timeout("agent:main:test", 0.0)
