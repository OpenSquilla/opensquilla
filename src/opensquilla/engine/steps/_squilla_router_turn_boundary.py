"""Private turn-boundary helpers for the Squilla router step."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast


def load_routing_history(
    *,
    session_key: str,
    metadata: dict,
    history_store: Any,
    max_entries: int,
    history_window_seconds: float,
    now: Callable[[], float],
    logger: Any,
) -> list[dict] | None:
    """Restore and trim per-session routing history before classification."""
    routing_history = cast(list[dict] | None, history_store.get(session_key))
    if not routing_history:
        persisted = metadata.get("routing_history")
        if persisted:
            current_time = now()
            routing_history = [
                {**entry, "_ts": current_time} if "_ts" not in entry else entry
                for entry in persisted
            ]
            history_store.set(session_key, routing_history)
            logger.debug(
                "squilla_router.history_cold_start",
                session=session_key,
                restored=len(routing_history),
            )
    if routing_history:
        cutoff = now() - history_window_seconds
        routing_history = [
            entry for entry in routing_history if entry.get("_ts", 0) > cutoff
        ]
        routing_history = routing_history[-max_entries:]
        history_store.set(session_key, routing_history)
    logger.debug(
        "squilla_router.history_loaded",
        session=session_key,
        history_len=len(routing_history) if routing_history else 0,
    )
    return cast(list[dict] | None, routing_history)


def finalize_history_decision(
    *,
    decision: Any,
    router_cfg: object,
    tiers: dict,
    valid_tiers: list[str],
    message: str,
    routing_history: list[dict] | None,
    strategy_name: str,
    extra: dict,
    thinking_mode: str | None,
    prompt_policy: str | None,
    finalize_decision: Callable[..., Any],
    reconcile_controller: Callable[[str | None, str | None, dict], tuple[str | None, str | None]],
) -> tuple[Any, str | None, str | None]:
    """Apply history-aware finalization and keep controller metadata aligned."""
    finalized = finalize_decision(
        decision,
        router_cfg=router_cfg,
        tiers=tiers,
        valid_tiers=valid_tiers,
        message=message,
        routing_history=routing_history,
        strategy_name=strategy_name,
        extra=extra,
    )
    reconciled_thinking_mode, reconciled_prompt_policy = reconcile_controller(
        thinking_mode,
        prompt_policy,
        extra,
    )
    return finalized, reconciled_thinking_mode, reconciled_prompt_policy


def append_routing_history(
    *,
    session_key: str,
    metadata: dict,
    history_store: Any,
    message: str,
    extra: dict | None,
    decision_tier: str,
    max_entries: int,
    now: Callable[[], float],
    logger: Any,
) -> None:
    """Append the finalized routing decision to per-session turn history."""
    if not extra:
        return
    history = history_store.setdefault(session_key, [])
    entry = {
        "turn_index": len(history),
        "_ts": now(),
        "text": message,
        **extra,
        "base_tier": extra.get("base_tier", decision_tier),
        "final_tier": extra.get("final_tier", decision_tier),
        "final_route_class": extra.get("final_route_class"),
    }
    history.append(entry)
    if len(history) > max_entries:
        history_store.set(session_key, history[-max_entries:])
    metadata["routing_history"] = history_store.get(session_key)
    logger.debug(
        "squilla_router.history_appended",
        session=session_key,
        turn_index=entry["turn_index"],
        route_class=entry.get("route_class"),
        total_history=history_store.length(session_key),
    )
