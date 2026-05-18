"""Boundary tests for the pricing facade and internal modules."""

from __future__ import annotations


def test_pricing_facade_reexports_public_api_from_internal_modules() -> None:
    from opensquilla.engine import (
        _pricing_cache,
        _pricing_live,
        _pricing_static,
        _pricing_types,
        pricing,
    )

    assert pricing.ModelPrice is _pricing_types.ModelPrice
    assert pricing.PriceEntry is _pricing_types.PriceEntry
    assert pricing.PricingCache is _pricing_cache.PricingCache
    assert pricing.lookup_price is _pricing_live.lookup_price
    assert pricing.refresh_live_prices is _pricing_live.refresh_live_prices
    assert (
        pricing.reset_live_price_cache_for_tests
        is _pricing_live.reset_live_price_cache_for_tests
    )
    assert pricing.seed_live_price_cache_for_tests is _pricing_live.seed_live_price_cache_for_tests

    assert callable(_pricing_static._lookup_static_price)
    assert callable(_pricing_static._lookup_price_override)
    assert callable(_pricing_live._fetch_live_openrouter_price)
    assert callable(_pricing_live._select_official_endpoint_price)


def test_pricing_live_internal_selects_official_non_discount_endpoint() -> None:
    from opensquilla.engine import _pricing_live

    price = _pricing_live._select_official_endpoint_price(
        {
            "data": {
                "endpoints": [
                    {
                        "provider_name": "Routed",
                        "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
                    },
                    {
                        "provider_name": "Moonshot AI",
                        "pricing": {
                            "prompt": "0.000001",
                            "completion": "0.000004",
                            "discount": 0.5,
                        },
                    },
                ]
            }
        },
        "moonshotai/kimi-k2.6",
    )

    assert price == _pricing_live.PriceEntry(input_per_m=2.0, output_per_m=8.0)
