"""CLI tests for `opensquilla onboard` and `configure`."""

from __future__ import annotations

import tomllib

from typer.testing import CliRunner

from opensquilla.cli.main import app

runner = CliRunner()


def test_onboard_noninteractive_provider(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    result = runner.invoke(
        app,
        [
            "onboard",
            "--provider", "openrouter",
            "--model", "deepseek/deepseek-v4-flash",
            "--api-key", "sk",
            "--skip-channels", "--skip-search",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "openrouter" in target.read_text()
    assert "sk" not in result.stdout


def test_onboard_noninteractive_provider_can_use_env_key_and_router(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    result = runner.invoke(
        app,
        [
            "onboard",
            "--provider",
            "deepseek",
            "--model",
            "deepseek-chat",
            "--api-key-env",
            "DEEPSEEK_API_KEY",
            "--router",
            "recommended",
            "--minimal",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "deepseek"
    assert data["llm"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert "api_key" not in data["llm"]
    assert data["squilla_router"]["tier_profile"] == "deepseek"
    assert "tiers" not in data["squilla_router"]
    assert "DEEPSEEK_API_KEY" in result.stdout


def test_onboard_noninteractive_provider_can_omit_model_for_router_profile(
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    result = runner.invoke(
        app,
        [
            "onboard",
            "--provider",
            "deepseek",
            "--api-key-env",
            "DEEPSEEK_API_KEY",
            "--minimal",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "deepseek"
    assert data["llm"]["model"] == "deepseek-v4-flash"
    assert data["squilla_router"]["tier_profile"] == "deepseek"


def test_onboard_noninteractive_provider_without_router_profile_disables_router(
    tmp_path, monkeypatch
):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "onboard",
            "--provider",
            "anthropic",
            "--model",
            "claude-3-5-sonnet-latest",
            "--api-key-env",
            "ANTHROPIC_API_KEY",
            "--minimal",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "anthropic"
    assert data["llm"]["api_key_env"] == "ANTHROPIC_API_KEY"
    assert "api_key" not in data["llm"]
    assert data["squilla_router"]["enabled"] is False


def test_onboard_if_needed_skips_when_configured(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    runner.invoke(
        app,
        [
            "onboard",
            "--provider", "openrouter",
            "--model", "x", "--api-key", "k",
            "--skip-channels", "--skip-search",
        ],
    )
    mtime_before = target.stat().st_mtime
    result = runner.invoke(app, ["onboard", "--if-needed"])
    assert result.exit_code == 0
    assert "already complete" in result.stdout.lower()
    assert target.stat().st_mtime == mtime_before


def test_onboard_if_needed_skips_when_key_comes_from_env(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    target.write_text(
        '[llm]\n'
        'provider = "openrouter"\n'
        'model = "deepseek/deepseek-v4-flash"\n'
        'api_key_env = "OPENROUTER_API_KEY"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(app, ["onboard", "--if-needed"])

    assert result.exit_code == 0
    assert "already complete" in result.stdout.lower()


def test_configure_provider_noninteractive_uses_setup_engine(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "provider",
            "--provider",
            "openrouter",
            "--model",
            "deepseek/deepseek-v4-flash",
            "--api-key-env",
            "OPENROUTER_API_KEY",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "openrouter"
    assert data["llm"]["api_key_env"] == "OPENROUTER_API_KEY"
    assert "api_key" not in data["llm"]


def test_configure_provider_can_omit_model_for_router_profile(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "provider",
            "--provider",
            "deepseek",
            "--api-key-env",
            "DEEPSEEK_API_KEY",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "deepseek"
    assert data["llm"]["model"] == "deepseek-v4-flash"


def test_configure_provider_recomputes_existing_router_profile(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    target.write_text(
        '[llm]\nprovider = "deepseek"\nmodel = "deepseek-chat"\n'
        '[squilla_router]\ntier_profile = "deepseek"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "provider",
            "--provider",
            "openai",
            "--model",
            "gpt-5.4-mini",
            "--api-key-env",
            "OPENAI_API_KEY",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["llm"]["provider"] == "openai"
    assert data["squilla_router"]["tier_profile"] == "openai"
    assert "tiers" not in data["squilla_router"]


def test_configure_router_noninteractive_can_disable(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    target.write_text(
        '[llm]\nprovider = "openrouter"\nmodel = "deepseek/deepseek-v4-flash"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(app, ["configure", "router", "--router", "disabled"])

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["squilla_router"]["enabled"] is False


def test_configure_router_invalid_mode_reports_clean_error(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    target.write_text(
        '[llm]\nprovider = "deepseek"\nmodel = "deepseek-chat"\n'
        '[squilla_router]\ntier_profile = "deepseek"\n',
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(app, ["configure", "router", "--router", "openrouter-mix"])

    assert result.exit_code == 2
    assert "openrouter-mix router mode is only valid" in result.output
    assert "Traceback" not in result.output
    assert target.read_text(encoding="utf-8") == before


def test_configure_search_noninteractive(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        ["configure", "search", "--search-provider", "duckduckgo", "--max-results", "7"],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["search_provider"] == "duckduckgo"
    assert data["search_max_results"] == 7


def test_configure_search_can_use_env_key_reference(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "search",
            "--search-provider",
            "brave",
            "--api-key-env",
            "BRAVE_SEARCH_API_KEY",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["search_provider"] == "brave"
    assert data["search_api_key_env"] == "BRAVE_SEARCH_API_KEY"
    assert "search_api_key" not in data


def test_configure_channel_noninteractive_adds_slack(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "channel",
            "--channel-type",
            "slack",
            "--name",
            "work",
            "--token",
            "xoxb-secret",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["channels"]["channels"][0]["type"] == "slack"
    assert data["channels"]["channels"][0]["name"] == "work"


def test_configure_image_generation_noninteractive_uses_env(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-image-env")

    result = runner.invoke(
        app,
        [
            "configure",
            "image-generation",
            "--image-provider",
            "openrouter",
            "--primary",
            "openrouter/google/gemini-3.1-flash-image-preview",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["image_generation"]["enabled"] is True
    assert data["image_generation"]["providers"]["openrouter"]["api_key"] == ""


def test_configure_memory_embedding_noninteractive(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(
        app,
        [
            "configure",
            "memory-embedding",
            "--memory-provider",
            "local",
            "--onnx-dir",
            "models/bge",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = tomllib.loads(target.read_text())
    assert data["memory"]["embedding"]["provider"] == "local"
    assert data["memory"]["embedding"]["local"]["onnx_dir"] == "models/bge"


def test_onboard_without_tty_prints_hint_without_writing_config(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 2
    assert "requires a TTY" in result.stdout
    assert "--api-key-env" in result.stdout
    assert "--router" in result.stdout
    assert not target.exists()


def test_init_help_mentions_onboard():
    result = runner.invoke(app, ["init", "--help"])
    assert "onboard" in result.stdout.lower()
