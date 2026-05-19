"""Result normalization helpers for the V4 Phase 3 router adapter."""

from __future__ import annotations

from typing import Any

import structlog

from opensquilla.squilla_router.controller import TIER_ORDER, select_localized_prompt_hint

log = structlog.get_logger(__name__)

ROUTE_CLASS_TO_TIER: dict[str, str] = {
    "R0": "t0",
    "R1": "t1",
    "R2": "t2",
    "R3": "t3",
}


def find_valid_tier(start_tier: str, valid_tiers: list[str]) -> str:
    if not valid_tiers:
        return "t1"
    start_idx = TIER_ORDER.index(start_tier) if start_tier in TIER_ORDER else 1
    for idx in range(start_idx, len(TIER_ORDER)):
        if TIER_ORDER[idx] in valid_tiers:
            return TIER_ORDER[idx]
    for tier in TIER_ORDER:
        if tier in valid_tiers:
            return tier
    return valid_tiers[0]


def route_class_for_tier(tier: str) -> str:
    return next((key for key, value in ROUTE_CLASS_TO_TIER.items() if value == tier), "R1")


def normalize_unavailable_adapter_result(
    *,
    valid_tiers: list[str],
    model_version: str,
    source: str,
) -> tuple[str, float, str, dict[str, Any]]:
    tier = find_valid_tier("t1", valid_tiers)
    route_class = route_class_for_tier(tier)
    return tier, 0.0, source, {
        "route_class": route_class,
        "top1_label": route_class,
        "thinking_mode": "T1",
        "prompt_policy": "P1",
        "model_version": model_version,
    }


def normalize_adapter_result(
    result: Any,
    *,
    valid_tiers: list[str],
    message: str,
    model_version: str,
    runtime_config: dict[str, Any],
    source: str,
) -> tuple[str, float, str, dict[str, Any]]:
    decision = result.decision
    route_class = str(getattr(decision, "route_class", "R1"))
    tier = ROUTE_CLASS_TO_TIER.get(route_class, "t1")
    if tier not in valid_tiers:
        tier = find_valid_tier(tier, valid_tiers)

    probabilities = dict(getattr(result, "probabilities", {}) or {})
    confidence = float(probabilities.get(route_class, 0.0))
    thinking_mode = getattr(decision, "thinking_mode", None)
    prompt_policy = getattr(decision, "prompt_policy", None)
    if thinking_mode is None:
        log.warning("v4_phase3.missing_thinking_mode", route_class=route_class)
        thinking_mode = "T0"
    if prompt_policy is None:
        log.warning("v4_phase3.missing_prompt_policy", route_class=route_class)
        prompt_policy = "P0"

    difficulty = float(getattr(decision, "difficulty_score", 0.0))
    intermediates = dict(getattr(result, "intermediates", {}) or {})
    extra: dict[str, Any] = {
        "route_class": route_class,
        "top1_label": route_class,
        "probabilities": probabilities,
        "difficulty": difficulty,
        "difficulty_score": difficulty,
        "margin": float(getattr(decision, "margin", 0.0)),
        "thinking_mode": str(thinking_mode),
        "prompt_policy": str(prompt_policy),
        "flags": dict(getattr(decision, "flags", {}) or {}),
        "aux_decision_probs": getattr(result, "aux_decision_probs", None),
        "aux_downgrade_applied": bool(getattr(decision, "aux_downgrade_applied", False)),
        "sticky_applied": bool(getattr(decision, "sticky_applied", False)),
        "selected_model": getattr(decision, "selected_model", None),
        "model_version": model_version,
    }
    prompt_hint = select_prompt_hint(
        runtime_config,
        str(prompt_policy),
        message,
    ) or intermediates.get("prompt_hint")
    if prompt_hint:
        extra["prompt_hint"] = str(prompt_hint)
    return tier, confidence, source, extra


def select_prompt_hint(
    runtime_config: dict[str, Any],
    prompt_policy: str,
    message: str | None = None,
) -> str | None:
    policy_cfg = runtime_config.get("prompt_policies", {}).get(prompt_policy, {})
    return select_localized_prompt_hint(policy_cfg, message)
