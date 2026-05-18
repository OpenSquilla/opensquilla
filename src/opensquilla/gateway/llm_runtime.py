"""Gateway compatibility facade for provider runtime config resolution."""

from __future__ import annotations

from opensquilla.provider.runtime_config import (
    OPENROUTER_DEFAULT_PROVIDER_ROUTING,
    LlmRuntimeConfig,
    provider_base_url_env_name,
    resolve_llm_runtime_config,
)

__all__ = [
    "LlmRuntimeConfig",
    "OPENROUTER_DEFAULT_PROVIDER_ROUTING",
    "provider_base_url_env_name",
    "resolve_llm_runtime_config",
]
