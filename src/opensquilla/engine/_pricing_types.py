"""Shared pricing value types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelPrice:
    """Per-token cost for a model (USD)."""

    input_per_token: float
    output_per_token: float


@dataclass
class PriceEntry:
    """Pricing per 1M tokens in USD."""

    input_per_m: float
    output_per_m: float
