"""Live OpenRouter pricing lookup and cache internals."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, cast

import httpx
import structlog

from opensquilla.env import trust_env as _trust_env
from opensquilla.provider.openrouter_attribution import openrouter_app_headers

from ._pricing_static import _lookup_price_override, _lookup_static_price
from ._pricing_types import PriceEntry

log = structlog.get_logger(__name__)

_CACHE_TTL = 3600  # 1 hour
_HTTP_TIMEOUT = 3.0
_OPENROUTER_PRICING_BASE_URL = "https://openrouter.ai/api/v1"
_LIVE_PRICE_MISS_TTL = 300

_PRICE_LOCK = threading.RLock()
_LIVE_PRICE_CACHE: dict[str, PriceEntry] = {}
_LIVE_PRICE_FETCHED_AT: dict[str, float] = {}
_LIVE_PRICE_MISS_AT: dict[str, float] = {}


def _live_pricing_enabled() -> bool:
    raw = os.environ.get("OPENSQUILLA_OPENROUTER_LIVE_PRICING", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _normalize_openrouter_base_url(base_url: str | None = None) -> str:
    base = base_url or os.environ.get("OPENROUTER_BASE_URL") or _OPENROUTER_PRICING_BASE_URL
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return base
    if base.endswith("/api"):
        return f"{base}/v1"
    return base


def _openrouter_endpoint_url(model_id: str, base_url: str | None = None) -> str:
    base = _normalize_openrouter_base_url(base_url)
    return f"{base}/models/{model_id}/endpoints"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _apply_discount_inverse(price_per_token: float, discount: float) -> float:
    """Return the non-discounted token price when OpenRouter reports a discount.

    OpenRouter endpoint pricing also includes cache-read rates. Those are not
    used here: Squilla Router savings and OpenSquilla estimates must use the normal
    prompt/completion price, then remove any explicit endpoint discount.
    """
    if discount <= 0:
        return price_per_token
    rate = discount / 100 if discount > 1 else discount
    if rate <= 0 or rate >= 1:
        return price_per_token
    return price_per_token / (1 - rate)


def _endpoint_price(entry: dict) -> PriceEntry | None:
    pricing = entry.get("pricing") or {}
    prompt = _float_or_none(pricing.get("prompt"))
    completion = _float_or_none(pricing.get("completion"))
    if prompt is None or completion is None:
        return None
    discount = _float_or_none(pricing.get("discount")) or 0.0
    return PriceEntry(
        input_per_m=_apply_discount_inverse(prompt, discount) * 1_000_000,
        output_per_m=_apply_discount_inverse(completion, discount) * 1_000_000,
    )


def _normalize_provider_token(value: object) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _official_provider_tokens(model_id: str) -> set[str]:
    namespace = model_id.split("/", 1)[0]
    normalized = _normalize_provider_token(namespace)
    aliases = {
        "zai": {"zai"},
        "moonshotai": {"moonshotai", "moonshot"},
    }
    return aliases.get(normalized, {normalized})


def _is_official_endpoint(model_id: str, endpoint: dict) -> bool:
    official = _official_provider_tokens(model_id)
    provider_name = _normalize_provider_token(endpoint.get("provider_name"))
    tag_root = str(endpoint.get("tag") or "").split("/", 1)[0]
    tag = _normalize_provider_token(tag_root)
    return provider_name in official or tag in official


def _select_official_endpoint_price(data: dict, model_id: str) -> PriceEntry | None:
    """Select a live OpenRouter price from model endpoint metadata.

    The public ``/models`` list can expose a cheap routed/top-provider price.
    For savings display we need the official provider's non-cache,
    non-discount prompt/completion price. Prefer the endpoint whose
    ``provider_name`` or tag matches the model namespace, then fall back to the
    first priced endpoint if OpenRouter has no owner endpoint for that model.
    """
    model = data.get("data") or data
    endpoints = model.get("endpoints") or []
    if not endpoints:
        return _endpoint_price(model)

    for endpoint in endpoints:
        if _is_official_endpoint(model_id, endpoint):
            price = _endpoint_price(endpoint)
            if price is not None:
                return price
    for endpoint in endpoints:
        price = _endpoint_price(endpoint)
        if price is not None:
            return price
    return None


def _fetch_openrouter_json_sync(url: str) -> dict:
    with httpx.Client(timeout=_HTTP_TIMEOUT, trust_env=_trust_env()) as client:
        resp = client.get(url, headers=openrouter_app_headers(url))
        resp.raise_for_status()
        return cast(dict[Any, Any], resp.json())


def _fetch_live_openrouter_price(model_id: str, base_url: str | None = None) -> PriceEntry | None:
    override = _lookup_price_override(model_id)
    if override is not None:
        return override
    try:
        data = _fetch_openrouter_json_sync(_openrouter_endpoint_url(model_id, base_url))
    except Exception as exc:
        log.debug("pricing.live_lookup_failed", model=model_id, error=str(exc))
        return None
    price = _select_official_endpoint_price(data, model_id)
    if price is not None:
        log.debug(
            "pricing.live_lookup_ready",
            model=model_id,
            input_per_m=price.input_per_m,
            output_per_m=price.output_per_m,
        )
    return price


def _should_fetch_live_price(model_id: str) -> bool:
    model_lower = model_id.lower().strip()
    if not _live_pricing_enabled():
        return False
    if "/" not in model_lower:
        return False
    if model_lower.startswith(("baai/", "sentence-transformers/", "ollama/", "local/")):
        return False
    return True


def refresh_live_prices(
    model_ids: list[str] | tuple[str, ...] | set[str],
    base_url: str | None = None,
) -> None:
    """Preload live OpenRouter endpoint prices for known model IDs."""
    for model_id in sorted({str(mid).strip() for mid in model_ids if str(mid).strip()}):
        override = _lookup_price_override(model_id)
        if override is not None:
            now = time.monotonic()
            key = model_id.lower()
            with _PRICE_LOCK:
                _LIVE_PRICE_CACHE[key] = override
                _LIVE_PRICE_FETCHED_AT[key] = now
                _LIVE_PRICE_MISS_AT.pop(key, None)
            continue
        if not _should_fetch_live_price(model_id):
            continue
        price = _fetch_live_openrouter_price(model_id, base_url)
        now = time.monotonic()
        key = model_id.lower()
        with _PRICE_LOCK:
            if price is None:
                _LIVE_PRICE_MISS_AT[key] = now
                continue
            _LIVE_PRICE_CACHE[key] = price
            _LIVE_PRICE_FETCHED_AT[key] = now
            _LIVE_PRICE_MISS_AT.pop(key, None)


def reset_live_price_cache_for_tests() -> None:
    with _PRICE_LOCK:
        _LIVE_PRICE_CACHE.clear()
        _LIVE_PRICE_FETCHED_AT.clear()
        _LIVE_PRICE_MISS_AT.clear()


def seed_live_price_cache_for_tests(model_id: str, price: PriceEntry) -> None:
    with _PRICE_LOCK:
        key = model_id.lower()
        _LIVE_PRICE_CACHE[key] = price
        _LIVE_PRICE_FETCHED_AT[key] = time.monotonic()
        _LIVE_PRICE_MISS_AT.pop(key, None)


def lookup_price(model_id: str) -> PriceEntry:
    """Look up pricing, preferring live OpenRouter endpoint prices.

    Live lookup uses ``prompt``/``completion`` endpoint prices, explicitly not
    cache-read prices. If OpenRouter is unreachable, the static table is only a
    fail-open fallback so cost estimation keeps working offline.
    """
    model_id = str(model_id or "").strip()
    override = _lookup_price_override(model_id)
    if override is not None:
        return override
    if not _should_fetch_live_price(model_id):
        return _lookup_static_price(model_id)

    now = time.monotonic()
    key = model_id.lower()
    with _PRICE_LOCK:
        cached = _LIVE_PRICE_CACHE.get(key)
        fetched_at = _LIVE_PRICE_FETCHED_AT.get(key, 0.0)
        if cached is not None and now - fetched_at <= _CACHE_TTL:
            return cached
        miss_at = _LIVE_PRICE_MISS_AT.get(key, 0.0)
        if miss_at and now - miss_at <= _LIVE_PRICE_MISS_TTL:
            return _lookup_static_price(model_id)

    price = _fetch_live_openrouter_price(model_id)
    with _PRICE_LOCK:
        if price is None:
            _LIVE_PRICE_MISS_AT[key] = time.monotonic()
            return _lookup_static_price(model_id)
        _LIVE_PRICE_CACHE[key] = price
        _LIVE_PRICE_FETCHED_AT[key] = time.monotonic()
        _LIVE_PRICE_MISS_AT.pop(key, None)
        return price
