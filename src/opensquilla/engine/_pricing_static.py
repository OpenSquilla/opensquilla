"""Static pricing table and override helpers."""

from __future__ import annotations

from ._pricing_types import ModelPrice, PriceEntry

# Canonical non-discount prices that must override OpenRouter's promotional or routed
# discounted prices. Values are USD per 1M tokens from official provider pricing.
_PRICE_OVERRIDES: list[tuple[str, PriceEntry]] = [
    ("deepseek/deepseek-v4-pro", PriceEntry(1.74, 3.48)),
]


def _lookup_price_override(model_id: str) -> PriceEntry | None:
    model_lower = str(model_id or "").strip().lower()
    for prefix, entry in _PRICE_OVERRIDES:
        if model_lower.startswith(prefix):
            return entry
    return None


def _model_price_from_entry(entry: PriceEntry) -> ModelPrice:
    return ModelPrice(
        input_per_token=entry.input_per_m / 1_000_000,
        output_per_token=entry.output_per_m / 1_000_000,
    )


# Built-in pricing table: model_prefix -> (input_per_M, output_per_M)
_PRICING_TABLE: list[tuple[str, PriceEntry]] = [
    # Offline fallback for Squilla Router tier models.
    ("stepfun/step-3.5-flash", PriceEntry(0.10, 0.30)),
    ("z-ai/glm-4.5-air", PriceEntry(0.13, 0.85)),
    ("minimax/minimax-m2.5", PriceEntry(0.118, 0.99)),
    ("deepseek/deepseek-v4-flash", PriceEntry(0.14, 0.28)),
    ("deepseek/deepseek-v4-pro", PriceEntry(1.74, 3.48)),
    ("deepseek/deepseek-v3.2", PriceEntry(0.26, 0.38)),
    ("z-ai/glm-5.1", PriceEntry(1.40, 4.40)),
    ("z-ai/glm-5", PriceEntry(0.72, 2.30)),
    ("moonshotai/kimi-k2.6", PriceEntry(0.95, 4.0)),
    ("moonshotai/kimi-k2.5", PriceEntry(0.3827, 1.72)),
    # Direct provider smoke estimates.
    ("gpt-4.1", PriceEntry(2.0, 8.0)),
    # Zhipu docs quote GLM-4.5 series API prices in CNY; converted to USD at
    # roughly 6.975 CNY/USD for OpenSquilla estimates only.
    ("glm-4.5", PriceEntry(0.115, 0.287)),
    ("kimi-k2.6", PriceEntry(0.95, 4.0)),
    ("minimax-m2.7", PriceEntry(0.118, 0.99)),
    # Direct provider profile estimates.
    # OpenAI-compatible Chat Completions returns token usage, not billed cost.
    # These values prevent profile defaults from falling through to generic
    # fallback pricing and must be reported as OpenSquilla estimates.
    ("gpt-5.4-nano", PriceEntry(0.20, 1.25)),
    ("gpt-5.4-mini", PriceEntry(0.75, 4.50)),
    ("gpt-5.5", PriceEntry(5.0, 30.0)),
    ("glm-5.1", PriceEntry(1.40, 4.40)),
    ("glm-5", PriceEntry(0.72, 2.30)),
    ("kimi-k2.5", PriceEntry(0.3827, 1.72)),
    ("deepseek-v4-flash", PriceEntry(0.14, 0.28)),
    ("deepseek-v4-pro", PriceEntry(1.74, 3.48)),
    ("gemini-2.5-flash-lite", PriceEntry(0.10, 0.40)),
    ("gemini-2.5-flash", PriceEntry(0.15, 0.60)),
    ("gemini-2.5-pro", PriceEntry(1.25, 10.0)),
    ("qwen3.6-flash", PriceEntry(0.029, 0.287)),
    ("qwen3.6-plus", PriceEntry(0.115, 0.688)),
    ("qwen3-max", PriceEntry(0.359, 1.434)),
    ("doubao-seed-1-6-flash", PriceEntry(0.15, 0.60)),
    ("doubao-seed-1-6-thinking", PriceEntry(0.60, 2.40)),
    ("doubao-seed-1-6", PriceEntry(0.30, 1.20)),
    # Volcengine Ark online inference Seed 2.0 estimates for <=32k input tier,
    # converted from CNY per 1M tokens to USD at roughly 6.975 CNY/USD.
    ("doubao-seed-2-0-mini-260215", PriceEntry(0.029, 0.287)),
    ("doubao-seed-2-0-lite-260215", PriceEntry(0.086, 0.516)),
    ("doubao-seed-2-0-pro-260215", PriceEntry(0.459, 2.294)),
    ("doubao-seed-2-0-code-preview-260215", PriceEntry(0.459, 2.294)),
    # DeepSeek.
    ("deepseek/deepseek-r1", PriceEntry(0.70, 2.50)),
    ("deepseek/deepseek-v3", PriceEntry(0.26, 0.38)),
    ("deepseek/deepseek-chat", PriceEntry(0.14, 0.28)),
    # OpenAI (OpenRouter prices).
    ("openai/gpt-4.1-mini", PriceEntry(0.40, 1.60)),
    ("openai/gpt-4.1", PriceEntry(2.0, 8.0)),
    ("openai/gpt-4o-mini", PriceEntry(0.15, 0.60)),
    ("openai/gpt-4o", PriceEntry(2.50, 10.0)),
    ("openai/text-embedding-3-small", PriceEntry(0.02, 0.0)),
    ("openai/text-embedding-3-large", PriceEntry(0.13, 0.0)),
    ("gpt-4o-mini", PriceEntry(0.15, 0.60)),
    ("gpt-4o", PriceEntry(2.50, 10.0)),
    ("text-embedding-3-small", PriceEntry(0.02, 0.0)),
    ("text-embedding-3-large", PriceEntry(0.13, 0.0)),
    ("gpt-4-turbo", PriceEntry(10.0, 30.0)),
    ("gpt-4-", PriceEntry(30.0, 60.0)),
    ("o3-mini", PriceEntry(1.10, 4.40)),
    ("o1-mini", PriceEntry(3.0, 12.0)),
    ("o1", PriceEntry(15.0, 60.0)),
    # Anthropic Claude.
    ("anthropic/claude-opus-4.7", PriceEntry(5.0, 25.0)),
    ("anthropic/claude-opus-4.5", PriceEntry(5.0, 25.0)),
    ("anthropic/claude-opus-4", PriceEntry(15.0, 75.0)),
    ("anthropic/claude-sonnet-4", PriceEntry(3.0, 15.0)),
    ("anthropic/claude-3-5-sonnet", PriceEntry(3.0, 15.0)),
    ("anthropic/claude-3-5-haiku", PriceEntry(0.80, 4.0)),
    ("anthropic/claude-3-opus", PriceEntry(15.0, 75.0)),
    ("anthropic/claude-3-sonnet", PriceEntry(3.0, 15.0)),
    ("anthropic/claude-3-haiku", PriceEntry(0.25, 1.25)),
    ("claude-opus-4", PriceEntry(15.0, 75.0)),
    ("claude-sonnet-4", PriceEntry(3.0, 15.0)),
    ("claude-3-5-sonnet", PriceEntry(3.0, 15.0)),
    ("claude-3-5-haiku", PriceEntry(0.80, 4.0)),
    ("claude-3-opus", PriceEntry(15.0, 75.0)),
    ("claude-3-sonnet", PriceEntry(3.0, 15.0)),
    ("claude-3-haiku", PriceEntry(0.25, 1.25)),
    # Google Gemini.
    ("google/gemini-2.5-flash", PriceEntry(0.15, 0.60)),
    ("google/gemini-2.5-pro", PriceEntry(1.25, 10.0)),
    ("google/gemini-2.0-flash", PriceEntry(0.10, 0.40)),
    # Alibaba Cloud Model Studio / DashScope, Chinese Mainland (Beijing).
    # OpenAI-compatible Chat Completions returns token usage, not billed cost.
    # These prices are used only for OpenSquilla estimates and must not be
    # reported as provider-billed amounts. Source: Alibaba Cloud Model Studio
    # model pricing, checked 2026-05-03. Prices are USD per 1M tokens.
    ("qwen-plus", PriceEntry(0.115, 0.287)),
    ("qwen-flash", PriceEntry(0.022, 0.216)),
    ("qwen-turbo", PriceEntry(0.044, 0.087)),
    ("qwen-max", PriceEntry(0.345, 1.377)),
    # MiniMax.
    ("minimax/minimax-m2.7", PriceEntry(0.118, 0.99)),
    # Ollama / local (free).
    ("baai/", PriceEntry(0.0, 0.0)),
    ("sentence-transformers/", PriceEntry(0.0, 0.0)),
    ("ollama/", PriceEntry(0.0, 0.0)),
    ("local/", PriceEntry(0.0, 0.0)),
]

_DEFAULT_PRICING = PriceEntry(3.0, 15.0)


def _lookup_static_price(model_id: str) -> PriceEntry:
    override = _lookup_price_override(model_id)
    if override is not None:
        return override
    model_lower = model_id.lower()
    for prefix, entry in _PRICING_TABLE:
        if model_lower.startswith(prefix):
            return entry
    return _DEFAULT_PRICING
