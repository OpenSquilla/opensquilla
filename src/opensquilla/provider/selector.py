"""Model selector with fallback chain and config-driven provider resolution."""

from __future__ import annotations

from .config import ProviderBuildError, ProviderConfig, SelectorConfig
from .factory import (
    DEFAULT_PROVIDER_FACTORY,
    ProviderFactoryPort,
    build_provider_from_config,
)
from .protocol import LLMProvider, ProviderPlugin, resolve_failover_chain

__all__ = [
    "ModelSelector",
    "ProviderBuildError",
    "ProviderConfig",
    "SelectorConfig",
    "_build_provider",
    "build_provider",
]


def _build_provider(cfg: ProviderConfig) -> LLMProvider:
    """Compatibility wrapper for the historical private factory helper."""
    return build_provider_from_config(cfg)


class ModelSelector:
    """Resolves a provider from primary config with fallback chain support.

    Usage::

        selector = ModelSelector(SelectorConfig(
            primary=ProviderConfig("anthropic", "claude-sonnet-4-6", api_key="..."),
            fallbacks=[ProviderConfig("ollama", "llama3")],
        ))
        provider = selector.resolve()  # returns primary
        # on failure, call selector.next_fallback() to get next in chain
    """

    def __init__(
        self,
        config: SelectorConfig,
        plugin: ProviderPlugin | None = None,
        provider_factory: ProviderFactoryPort | None = None,
    ) -> None:
        self._config = config
        self._chain: list[ProviderConfig] = [config.primary, *config.fallbacks]
        self._index = 0
        self._plugin = plugin
        self._provider_factory = provider_factory or DEFAULT_PROVIDER_FACTORY

    def resolve(self) -> LLMProvider:
        """Return the current provider (primary on first call)."""
        return self._provider_factory.build(self._chain[self._index])

    def has_fallback(self) -> bool:
        """True if there is at least one more fallback available."""
        return self._index < len(self._chain) - 1

    def next_fallback(self) -> LLMProvider:
        """Advance to the next fallback and return it.

        Raises IndexError if no more fallbacks are available.
        """
        if not self.has_fallback():
            raise IndexError("No more provider fallbacks available")
        self._index += 1
        return self._provider_factory.build(self._chain[self._index])

    def next_fallback_after_failure(self, primary_failure: Exception) -> LLMProvider:
        """Advance to the next fallback, consulting ``plugin.failover_hook``.

        When a plugin is registered its ``failover_hook`` return value
        replaces the static fallback chain from ``SelectorConfig``. An
        empty chain raises ``IndexError`` exactly like ``next_fallback``.
        """
        chain = resolve_failover_chain(primary_failure, self._config, self._plugin)
        if not chain:
            raise IndexError("No fallback chain available")
        self._chain = [self._chain[0], *chain]
        self._index = 1
        return self._provider_factory.build(self._chain[self._index])

    def override_model(self, model: str) -> None:
        """Update the model on the primary provider config (for runtime switching)."""
        if model and model != self._chain[0].model:
            self._chain[0] = ProviderConfig(
                provider=self._chain[0].provider,
                model=model,
                api_key=self._chain[0].api_key,
                base_url=self._chain[0].base_url,
                org_id=self._chain[0].org_id,
                proxy=self._chain[0].proxy,
                provider_routing=self._chain[0].provider_routing,
            )

    def sync_primary(self, cfg: ProviderConfig) -> None:
        """Replace the primary provider config for future resolves and clones."""
        self._config.primary = cfg
        self._chain[0] = cfg
        self.reset()

    def reset(self) -> None:
        """Reset to primary provider."""
        self._index = 0

    def clone(self) -> ModelSelector:
        """Return an independent copy for concurrent use.

        The clone starts at index 0 with its own chain list, so mutations
        (override_model, next_fallback) don't affect the original.
        """
        return ModelSelector(
            self._config,
            plugin=self._plugin,
            provider_factory=self._provider_factory,
        )

    async def list_models(self) -> list[dict]:
        """Aggregate models from all configured providers in the chain."""
        models: list[dict] = []
        for cfg in self._chain:
            try:
                provider = self._provider_factory.build(cfg)
                provider_models = await provider.list_models()
                models.extend(m.model_dump() for m in provider_models)
            except Exception:
                continue
        return models

    @property
    def current_config(self) -> ProviderConfig:
        return self._chain[self._index]


def build_provider(
    provider: str,
    model: str,
    api_key: str = "",
    base_url: str = "",
    org_id: str = "",
) -> LLMProvider:
    """Convenience factory: build a single provider directly."""
    return _build_provider(
        ProviderConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            org_id=org_id,
        )
    )
