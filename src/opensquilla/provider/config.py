"""Runtime provider selection configuration objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    """Runtime configuration for a single provider."""

    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    org_id: str = ""
    proxy: str = ""
    provider_routing: dict[str, str] = field(default_factory=dict)


@dataclass
class SelectorConfig:
    """Full model selection config: primary + ordered fallback chain."""

    primary: ProviderConfig
    fallbacks: list[ProviderConfig] = field(default_factory=list)


class ProviderBuildError(Exception):
    """Raised when a provider cannot be instantiated."""
