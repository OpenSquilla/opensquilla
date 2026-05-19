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


def test_onboarding_finish_output_separates_summary_from_commands():
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import format_next_steps

    text = format_next_steps(GatewayConfig(), config_path="C:/tmp/config.toml")

    assert text.startswith("Configuration summary:")
    assert "Next steps:" not in text
    assert "Commands:" in text
    assert "  Run gateway now: opensquilla gateway run" in text
    assert "  Start gateway in background: opensquilla gateway start --json" in text
    assert "  Restart running gateway: opensquilla gateway restart --json" in text
    assert "Reference:" in text
    assert "  Web UI: http://127.0.0.1:18791/control/" in text
    assert "uv run" not in text


def test_onboarding_finish_output_puts_missing_env_hint_in_commands(monkeypatch):
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import format_next_steps

    cfg = GatewayConfig()
    cfg.llm.api_key = ""
    cfg.llm.api_key_env = "OPENROUTER_API_KEY"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    text = format_next_steps(cfg, config_path="C:/tmp/config.toml")

    commands = text.split("Commands:", 1)[1].split("Reference:", 1)[0]
    reference = text.split("Reference:", 1)[1]
    assert 'Set key before starting gateway: export OPENROUTER_API_KEY="<your-key>"' in commands
    assert "Set key before starting gateway" not in reference


def test_onboarding_finish_output_keeps_provider_key_url_as_reference():
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import format_next_steps

    cfg = GatewayConfig()
    cfg.llm.provider = "openrouter"

    text = format_next_steps(cfg, config_path="C:/tmp/config.toml")

    assert "Reference:" in text
    assert "  Provider keys: https://openrouter.ai/keys" in text


def test_env_reference_warnings_cover_llm_and_search_missing_env(monkeypatch):
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import env_reference_warnings

    cfg = GatewayConfig()
    cfg.llm.api_key = ""
    cfg.llm.api_key_env = "OPENROUTER_API_KEY"
    cfg.search_provider = "brave"
    cfg.search_api_key = ""
    cfg.search_api_key_env = "BRAVE_SEARCH_API_KEY"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    warnings = env_reference_warnings(cfg)

    assert any(
        "LLM provider" in warning and "OPENROUTER_API_KEY" in warning
        for warning in warnings
    )
    assert any(
        "Search provider" in warning and "BRAVE_SEARCH_API_KEY" in warning
        for warning in warnings
    )


def test_env_reference_warnings_do_not_warn_for_image_generation_missing_env_when_disabled(
    monkeypatch,
):
    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.onboarding.next_steps import env_reference_warnings

    cfg = GatewayConfig()
    cfg.image_generation.enabled = False
    cfg.image_generation.providers.openrouter.api_key = ""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    warnings = env_reference_warnings(cfg)

    assert not any("Image generation" in warning for warning in warnings)
