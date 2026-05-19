"""Explicit provider factory for registry-backed provider construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .anthropic import AnthropicProvider
from .config import ProviderBuildError, ProviderConfig
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .protocol import LLMProvider
from .registry import ProviderSpec, UnknownProviderError, get_provider_spec

ProviderBuilder = Callable[[ProviderConfig, ProviderSpec, str], LLMProvider]


class ProviderFactoryPort(Protocol):
    """Minimal construction port consumed by selectors and application code."""

    def build(self, cfg: ProviderConfig) -> LLMProvider:
        """Instantiate a provider for ``cfg``."""
        ...


def _unsupported_runtime_message(provider: str) -> str:
    return (
        f"Provider '{provider}' is registered but runtime support "
        "is not enabled in this wave"
    )


def _missing_base_url_message(provider: str) -> str:
    return f"Provider '{provider}' requires an explicit base_url"


class ProviderFactory:
    """Build providers from registry metadata.

    The default factory preserves the historic construction behavior while
    making backend-to-adapter bindings explicit and overridable for tests or
    future plugin-loaded providers.
    """

    def __init__(self, builders: Mapping[str, ProviderBuilder] | None = None) -> None:
        self._builders: dict[str, ProviderBuilder] = {
            "anthropic": self._build_anthropic,
            "openai_compat": self._build_openai_compat,
            "ollama": self._build_ollama,
        }
        if builders:
            self._builders.update(builders)

    def register_backend(self, backend: str, builder: ProviderBuilder) -> None:
        """Register or replace the adapter builder for a provider backend."""
        self._builders[backend] = builder

    def build(self, cfg: ProviderConfig) -> LLMProvider:
        """Instantiate the provider implementation declared by ``cfg``."""
        try:
            spec = get_provider_spec(cfg.provider)
        except UnknownProviderError as exc:
            raise ProviderBuildError(str(exc)) from exc

        if not spec.runtime_supported:
            raise ProviderBuildError(_unsupported_runtime_message(cfg.provider))

        base_url = cfg.base_url or spec.default_base_url
        if not base_url and spec.provider_id in {"azure", "vllm"}:
            raise ProviderBuildError(_missing_base_url_message(cfg.provider))

        builder = self._builders.get(spec.backend)
        if builder is None:
            raise ProviderBuildError(_unsupported_runtime_message(cfg.provider))
        return builder(cfg, spec, base_url)

    def _build_anthropic(
        self,
        cfg: ProviderConfig,
        spec: ProviderSpec,
        base_url: str,
    ) -> LLMProvider:
        kwargs: dict[str, Any] = {"api_key": cfg.api_key, "model": cfg.model}
        if base_url:
            kwargs["base_url"] = base_url
        if cfg.proxy:
            kwargs["proxy"] = cfg.proxy
        return AnthropicProvider(**kwargs)

    def _build_openai_compat(
        self,
        cfg: ProviderConfig,
        spec: ProviderSpec,
        base_url: str,
    ) -> LLMProvider:
        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key,
            "model": cfg.model,
            "provider_kind": spec.provider_kind,
        }
        if base_url:
            kwargs["base_url"] = base_url
        if cfg.org_id:
            kwargs["org_id"] = cfg.org_id
        if cfg.proxy:
            kwargs["proxy"] = cfg.proxy
        if cfg.provider_routing:
            kwargs["provider_routing"] = cfg.provider_routing
        return OpenAIProvider(**kwargs)

    def _build_ollama(
        self,
        cfg: ProviderConfig,
        spec: ProviderSpec,
        base_url: str,
    ) -> LLMProvider:
        kwargs: dict[str, Any] = {"model": cfg.model}
        if base_url:
            kwargs["base_url"] = base_url
        if cfg.proxy:
            kwargs["proxy"] = cfg.proxy
        return OllamaProvider(**kwargs)


DEFAULT_PROVIDER_FACTORY = ProviderFactory()


def build_provider_from_config(
    cfg: ProviderConfig,
    factory: ProviderFactoryPort | None = None,
) -> LLMProvider:
    """Build a single provider using the default or injected factory."""
    return (factory or DEFAULT_PROVIDER_FACTORY).build(cfg)
