from types import SimpleNamespace

from opensquilla.squilla_router._v4_phase3_adapter import (
    normalize_adapter_result,
    normalize_unavailable_adapter_result,
)


def test_route_r0_falls_forward_to_t2_when_lower_tiers_are_unavailable() -> None:
    result = SimpleNamespace(
        decision=SimpleNamespace(
            route_class="R0",
            thinking_mode="T0",
            prompt_policy="P0",
            difficulty_score=0.1,
            margin=0.9,
            flags={},
            aux_downgrade_applied=False,
            sticky_applied=False,
            selected_model=None,
        ),
        probabilities={"R0": 0.92},
        intermediates={},
        aux_decision_probs=None,
    )

    tier, confidence, source, extra = normalize_adapter_result(
        result,
        valid_tiers=["t2", "t3"],
        message="short answer only",
        model_version="test-version",
        runtime_config={},
        source="v4_phase3",
    )

    assert tier == "t2"
    assert confidence == 0.92
    assert source == "v4_phase3"
    assert extra["route_class"] == "R0"
    assert extra["top1_label"] == "R0"


def test_unavailable_fallback_starts_from_t1_and_falls_forward_to_first_valid_tier() -> None:
    tier, confidence, source, extra = normalize_unavailable_adapter_result(
        valid_tiers=["t2", "t3"],
        model_version="test-version",
        source="v4_unavailable",
    )

    assert tier == "t2"
    assert confidence == 0.0
    assert source == "v4_unavailable"
    assert extra["route_class"] == "R2"
    assert extra["top1_label"] == "R2"


def test_runtime_config_localized_p0_prompt_hint_is_preserved_in_extra() -> None:
    result = SimpleNamespace(
        decision=SimpleNamespace(
            route_class="R1",
            thinking_mode="T0",
            prompt_policy="P0",
            difficulty_score=0.2,
            margin=0.7,
            flags={},
            aux_downgrade_applied=False,
            sticky_applied=False,
            selected_model=None,
        ),
        probabilities={"R1": 0.77},
        intermediates={},
        aux_decision_probs=None,
    )

    _tier, _confidence, _source, extra = normalize_adapter_result(
        result,
        valid_tiers=["t1", "t2", "t3"],
        message="请直接回答这个问题",
        model_version="test-version",
        runtime_config={
            "prompt_policies": {
                "P0": {
                    "hint_en": "Answer directly.",
                    "hint_zh": "直接回答。",
                }
            }
        },
        source="v4_phase3",
    )

    assert extra["prompt_policy"] == "P0"
    assert extra["prompt_hint"] == "直接回答。"
