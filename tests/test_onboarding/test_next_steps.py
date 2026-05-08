"""Tests for onboarding next-step guidance."""

from __future__ import annotations


def test_next_steps_uses_powershell_env_hint_on_windows(monkeypatch):
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding import next_steps

    cfg = GatewayConfig()
    cfg.llm.api_key = ""
    cfg.llm.api_key_env = "OPENROUTER_API_KEY"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(next_steps.platform, "system", lambda: "Windows")

    text = next_steps.format_next_steps(cfg, config_path="C:/tmp/config.toml")

    assert 'PowerShell: $env:OPENROUTER_API_KEY = "<your-key>"' in text
    assert "$OPENROUTER_API_KEY=<your-key>" not in text


def test_next_steps_warns_running_gateway_must_restart():
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import format_next_steps

    text = format_next_steps(GatewayConfig(), config_path="C:/tmp/config.toml")

    assert "If a gateway is already running, restart it so it loads this config." in text
    assert "uv run opensquilla gateway restart --json" in text
