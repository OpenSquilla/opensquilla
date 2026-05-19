"""OpenRouter model-list pricing cache."""

from __future__ import annotations

import time

import httpx
import structlog

from opensquilla.env import trust_env as _trust_env
from opensquilla.provider.openrouter_attribution import openrouter_app_headers

from ._pricing_live import _CACHE_TTL, _HTTP_TIMEOUT
from ._pricing_static import _lookup_price_override, _model_price_from_entry
from ._pricing_types import ModelPrice

log = structlog.get_logger(__name__)


class PricingCache:
    """Fetches and caches model pricing from OpenRouter /api/v1/models."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        ttl_seconds: int = _CACHE_TTL,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._ttl = ttl_seconds
        self._cache: dict[str, ModelPrice] = {}
        self._fetched_at: float = 0

    @property
    def is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at > self._ttl

    def get_price_sync(self, model_id: str) -> ModelPrice | None:
        """Get cached price without refreshing."""
        override = _lookup_price_override(model_id)
        if override is not None:
            return _model_price_from_entry(override)
        return self._cache.get(model_id)

    async def get_price(self, model_id: str) -> ModelPrice | None:
        """Get price, refreshing cache if stale."""
        override = _lookup_price_override(model_id)
        if override is not None:
            return _model_price_from_entry(override)
        if self.is_stale:
            await self.refresh()
        return self._cache.get(model_id)

    async def refresh(self) -> None:
        """Fetch model list from OpenRouter and update cache."""
        url = f"{self._base_url}/models"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        headers.update(openrouter_app_headers(self._base_url))
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, trust_env=_trust_env()) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            new_cache: dict[str, ModelPrice] = {}
            for model in data.get("data", []):
                model_id = model.get("id", "")
                pricing = model.get("pricing", {})
                override = _lookup_price_override(model_id)
                if override is not None:
                    new_cache[model_id] = _model_price_from_entry(override)
                    continue
                prompt_cost = pricing.get("prompt")
                completion_cost = pricing.get("completion")
                if prompt_cost is not None and completion_cost is not None:
                    try:
                        new_cache[model_id] = ModelPrice(
                            input_per_token=float(prompt_cost),
                            output_per_token=float(completion_cost),
                        )
                    except (ValueError, TypeError):
                        continue

            self._cache = new_cache
            self._fetched_at = time.monotonic()
            log.info("pricing.refreshed", models=len(new_cache))
        except Exception as exc:
            log.warning("pricing.refresh_failed", error=str(exc))
