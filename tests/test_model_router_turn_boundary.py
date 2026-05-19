from __future__ import annotations

import pytest

from opensquilla.engine.pipeline import TurnContext
from opensquilla.engine.steps import _squilla_router_turn_boundary  # noqa: F401
from opensquilla.engine.steps import squilla_router as squilla_router_step
from opensquilla.engine.steps.squilla_router import apply_squilla_router
from opensquilla.gateway.config import GatewayConfig


class CapturingStrategy:
    def __init__(self) -> None:
        self.routing_history_seen: list[dict] | None = None

    async def classify(
        self,
        message: str,
        valid_tiers: list[str],
        routing_history: list[dict] | None = None,
    ) -> tuple[str, float, str, dict]:
        self.routing_history_seen = [dict(entry) for entry in routing_history or []]
        return "t0", 0.1, "v4_phase3", {
            "route_class": "R0",
            "thinking_mode": "T0",
            "prompt_policy": "P0",
        }


@pytest.fixture(autouse=True)
def reset_squilla_router_state(monkeypatch: pytest.MonkeyPatch) -> None:
    squilla_router_step._history_store.clear()
    squilla_router_step._strategy = None
    squilla_router_step._strategy_key = None
    yield
    squilla_router_step._history_store.clear()
    squilla_router_step._strategy = None
    squilla_router_step._strategy_key = None
    monkeypatch.undo()


def make_context(*, session_key: str, restored_history: list[dict]) -> TurnContext:
    config = GatewayConfig()
    config.squilla_router.rollout_phase = "full"
    return TurnContext(
        message="Use the cheap route if confidence allows it.",
        session_key=session_key,
        config=config,
        provider=None,
        model=config.llm.model,
        tool_defs=[],
        system_prompt="system",
        metadata={"routing_history": restored_history},
    )


@pytest.mark.asyncio
async def test_restored_history_is_trimmed_for_strategy_and_appended_after_finalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = CapturingStrategy()
    monkeypatch.setattr(squilla_router_step, "_get_strategy", lambda _config: strategy)
    restored_history = [
        {
            "turn_index": index,
            "text": f"Restored turn {index}",
            "route_class": "R0",
            "base_tier": "t0",
            "final_tier": "t0",
            "final_route_class": "R0",
        }
        for index in range(7)
    ]
    ctx = make_context(session_key="turn-boundary-restored", restored_history=restored_history)

    routed = await apply_squilla_router(ctx)

    assert [entry["text"] for entry in strategy.routing_history_seen or []] == [
        "Restored turn 2",
        "Restored turn 3",
        "Restored turn 4",
        "Restored turn 5",
        "Restored turn 6",
    ]
    assert routed.metadata["routed_tier"] == "t1"

    stored_history = squilla_router_step._history_store.get(ctx.session_key)
    assert stored_history is not None
    appended = stored_history[-1]
    assert appended["text"] == "Use the cheap route if confidence allows it."
    assert appended["base_tier"] == "t0"
    assert appended["final_tier"] == "t1"
    assert appended["final_route_class"] == "R1"
    assert routed.metadata["routing_history"] == stored_history
