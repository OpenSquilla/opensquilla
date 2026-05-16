from __future__ import annotations

from typing import cast

import pytest

from opensquilla.provider import ProviderFactory, build_provider_from_config
from opensquilla.provider.anthropic import AnthropicProvider
from opensquilla.provider.config import ProviderBuildError, ProviderConfig, SelectorConfig
from opensquilla.provider.ollama import OllamaProvider
from opensquilla.provider.openai import OpenAIProvider
from opensquilla.provider.protocol import provider_metadata
from opensquilla.provider.registry import ProviderSpec
from opensquilla.provider.selector import ModelSelector


class _FakeProvider:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name


class _RecordingFactory:
    def __init__(self) -> None:
        self.configs: list[ProviderConfig] = []

    def build(self, cfg: ProviderConfig) -> _FakeProvider:
        self.configs.append(cfg)
        return _FakeProvider(f"fake-{cfg.provider}")


def test_default_factory_builds_registered_provider_adapters() -> None:
    openrouter = build_provider_from_config(
        ProviderConfig(provider="openrouter", model="openai/gpt-5-mini", api_key="test-key")
    )
    anthropic = build_provider_from_config(
        ProviderConfig(provider="anthropic", model="claude-sonnet-4-6", api_key="test-key")
    )
    ollama = build_provider_from_config(ProviderConfig(provider="ollama", model="llama3"))

    assert isinstance(openrouter, OpenAIProvider)
    assert provider_metadata(openrouter).provider_kind == "openrouter"
    assert provider_metadata(openrouter).base_url == "https://openrouter.ai/api/v1"
    assert isinstance(anthropic, AnthropicProvider)
    assert provider_metadata(anthropic).base_url == "https://api.anthropic.com"
    assert isinstance(ollama, OllamaProvider)
    assert provider_metadata(ollama).base_url == "http://localhost:11434"


def test_provider_factory_reports_unknown_or_unsupported_provider() -> None:
    with pytest.raises(ProviderBuildError, match="Unknown provider 'not-real'"):
        build_provider_from_config(ProviderConfig(provider="not-real", model="model"))

    with pytest.raises(ProviderBuildError, match="runtime support is not enabled"):
        build_provider_from_config(ProviderConfig(provider="github_copilot", model="model"))


def test_provider_factory_backend_builder_can_be_overridden() -> None:
    captured: dict[str, object] = {}

    def build_fake(
        cfg: ProviderConfig,
        spec: ProviderSpec,
        base_url: str,
    ) -> _FakeProvider:
        captured["cfg"] = cfg
        captured["spec"] = spec
        captured["base_url"] = base_url
        return _FakeProvider("custom-openai-compatible")

    factory = ProviderFactory({"openai_compat": build_fake})
    provider = factory.build(ProviderConfig(provider="openai", model="gpt-4o", api_key="key"))

    assert provider.provider_name == "custom-openai-compatible"
    assert captured["cfg"] == ProviderConfig(provider="openai", model="gpt-4o", api_key="key")
    assert cast(ProviderSpec, captured["spec"]).provider_id == "openai"
    assert captured["base_url"] == "https://api.openai.com/v1"


def test_provider_factory_backend_builder_can_be_registered_after_construction() -> None:
    def build_fake(
        cfg: ProviderConfig,
        spec: ProviderSpec,
        base_url: str,
    ) -> _FakeProvider:
        return _FakeProvider(f"{spec.provider_id}:{cfg.model}:{base_url}")

    factory = ProviderFactory()
    factory.register_backend("ollama", build_fake)

    provider = factory.build(ProviderConfig(provider="ollama", model="llama3"))

    assert provider.provider_name == "ollama:llama3:http://localhost:11434"


def test_model_selector_uses_injected_provider_factory_and_preserves_it_on_clone() -> None:
    factory = _RecordingFactory()
    selector = ModelSelector(
        SelectorConfig(
            primary=ProviderConfig(provider="openai", model="gpt-4o", api_key="key"),
            fallbacks=[ProviderConfig(provider="ollama", model="llama3")],
        ),
        provider_factory=factory,
    )

    primary = selector.resolve()
    fallback = selector.next_fallback()
    clone_primary = selector.clone().resolve()

    assert primary.provider_name == "fake-openai"
    assert fallback.provider_name == "fake-ollama"
    assert clone_primary.provider_name == "fake-openai"
    assert [cfg.provider for cfg in factory.configs] == ["openai", "ollama", "openai"]
