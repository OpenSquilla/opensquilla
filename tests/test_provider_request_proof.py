from __future__ import annotations

import json

import pytest

from opensquilla.provider.request_proof import (
    ProviderRequestBudgetExceeded,
    prove_or_compact_provider_payload,
    prove_provider_payload,
)


def test_provider_request_proof_allows_payload_within_budget() -> None:
    proof = prove_provider_payload(
        {
            "messages": [{"role": "user", "content": "small"}],
            "tools": [{"name": "tool", "description": "desc"}],
        },
        projection_adapter="openai",
        proof_budget=10_000,
    )

    assert proof["fits"] is True
    assert proof["projection_adapter"] == "openai"
    assert proof["estimated_chars"] < 10_000
    assert proof["messages_chars"] > 0
    assert proof["tools_chars"] > 0
    assert proof["system_chars"] == 0
    assert proof["top_level_chars"] == 0
    assert proof["tool_schema_too_large"] is False


def test_provider_request_proof_blocks_oversized_payload() -> None:
    with pytest.raises(ProviderRequestBudgetExceeded) as exc_info:
        prove_provider_payload(
            {"messages": [{"role": "user", "content": "x" * 5000}]},
            projection_adapter="openai",
            proof_budget=1000,
        )

    assert exc_info.value.proof["fits"] is False
    assert exc_info.value.proof["fallback_reason"] == "provider_request_budget_exhausted"
    assert exc_info.value.proof["top_contributors"][0]["chars"] == 5000


def test_provider_request_proof_uses_effective_budget_headroom() -> None:
    payload = {"messages": [{"role": "user", "content": "x" * 9400}]}

    with pytest.raises(ProviderRequestBudgetExceeded) as exc_info:
        prove_provider_payload(
            payload,
            projection_adapter="openrouter",
            proof_budget=10_000,
        )

    proof = exc_info.value.proof
    assert proof["fits"] is False
    assert proof["proof_budget"] == 10_000
    assert proof["raw_proof_budget"] == 10_000
    assert proof["effective_proof_budget"] < proof["raw_proof_budget"]
    assert proof["proof_headroom_chars"] > 0
    assert proof["estimated_chars"] <= proof["raw_proof_budget"]
    assert proof["estimated_chars"] > proof["effective_proof_budget"]


def test_provider_request_proof_excludes_native_image_payload_from_text_budget() -> None:
    proof = prove_provider_payload(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64," + ("a" * 5000),
                            },
                        },
                    ],
                }
            ]
        },
        projection_adapter="openrouter",
        proof_budget=1000,
        status_projection_mode="content_envelope",
    )

    assert proof["fits"] is True
    assert proof["media_blocks_excluded"] == 1
    assert proof["media_chars_excluded"] > 5000
    assert proof["top_contributors"][0]["chars"] < 5000


def test_provider_request_proof_excludes_anthropic_base64_media_from_text_budget() -> None:
    proof = prove_provider_payload(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "summarize this"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "a" * 5000,
                            },
                        },
                    ],
                }
            ]
        },
        projection_adapter="anthropic",
        proof_budget=1000,
        status_projection_mode="content_envelope",
    )

    assert proof["fits"] is True
    assert proof["media_blocks_excluded"] == 1
    assert proof["media_chars_excluded"] == 5000
    assert proof["top_contributors"][0]["chars"] < 5000


def test_provider_request_proof_still_blocks_large_text_next_to_native_media() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "x" * 5000},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + ("a" * 5000),
                        },
                    },
                ],
            }
        ]
    }

    with pytest.raises(ProviderRequestBudgetExceeded) as exc_info:
        prove_provider_payload(
            payload,
            projection_adapter="openrouter",
            proof_budget=1000,
            status_projection_mode="content_envelope",
        )

    proof = exc_info.value.proof
    assert proof["fits"] is False
    assert proof["media_blocks_excluded"] == 1
    assert proof["top_contributors"][0]["chars"] == 5000


def test_provider_request_proof_compacts_tool_payload_once() -> None:
    payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "x" * 5000},
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openai",
        proof_budget=2000,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["retry_count"] == 1
    assert len(compacted["messages"][1]["content"]) < 2000


def test_provider_request_proof_blocks_after_one_retry_when_still_oversized() -> None:
    payload = {"messages": [{"role": "tool", "content": "x" * 5000}]}

    with pytest.raises(ProviderRequestBudgetExceeded) as exc_info:
        prove_or_compact_provider_payload(
            payload,
            projection_adapter="openai",
            proof_budget=100,
            status_projection_mode="content_envelope",
        )

    assert exc_info.value.proof["fits"] is False
    assert exc_info.value.proof["retry_count"] == 2


def test_provider_request_proof_compacts_assistant_tool_call_arguments() -> None:
    large_arguments = json.dumps(
        {
            "cmd": "python build_report.py",
            "script": "print('start')\n" + ("x = 1\n" * 500) + "print('end')",
        }
    )
    payload = {
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "exec_command",
                            "arguments": large_arguments,
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openrouter",
        proof_budget=2200,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["retry_count"] == 2
    compacted_arguments = compacted["messages"][1]["tool_calls"][0]["function"][
        "arguments"
    ]
    parsed = json.loads(compacted_arguments)
    assert parsed["_opensquilla_compacted_tool_arguments"] is True
    assert parsed["original_chars"] == len(large_arguments)
    assert compacted_arguments != large_arguments
    assert payload["messages"][1]["tool_calls"][0]["function"]["arguments"] == large_arguments


def test_provider_request_proof_compacts_aggregate_current_turn_tool_arguments() -> None:
    tool_calls = []
    original_arguments: list[str] = []
    for index in range(36):
        arguments = json.dumps(
            {
                "path": f"generated/file-{index}.html",
                "content": "x" * 520,
            },
            separators=(",", ":"),
        )
        assert len(arguments) < 640
        original_arguments.append(arguments)
        tool_calls.append(
            {
                "id": f"call_{index}",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": arguments,
                },
            }
        )

    payload = {
        "messages": [
            {"role": "user", "content": "build the app"},
            {
                "role": "assistant",
                "tool_calls": tool_calls,
            },
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openrouter",
        proof_budget=13_000,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["compact_needed"] is True
    assert proof["aggregate_tool_arguments_compacted"] is True
    assert set(compacted) == {"messages"}
    compacted_arguments = [
        call["function"]["arguments"] for call in compacted["messages"][1]["tool_calls"]
    ]
    assert any(
        argument != original
        for argument, original in zip(compacted_arguments, original_arguments)
    )
    assert any(
        "_opensquilla_compacted_tool_arguments" in argument
        for argument in compacted_arguments
    )
    assert any('"path":"generated/file-0.html"' in argument for argument in compacted_arguments)
    assert any('"argument_keys":["content","path"]' in argument for argument in compacted_arguments)
    assert payload["messages"][1]["tool_calls"][0]["function"]["arguments"] == original_arguments[0]


def test_provider_request_proof_compacts_assistant_reasoning_content() -> None:
    payload = {
        "messages": [
            {"role": "user", "content": "continue"},
            {
                "role": "assistant",
                "content": "I will call a tool.",
                "reasoning_content": "thinking\n" + ("details\n" * 400),
            },
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openrouter",
        proof_budget=2200,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["retry_count"] == 2
    reasoning = compacted["messages"][1]["reasoning_content"]
    assert "[provider_request_reasoning_content_compacted:" in reasoning
    assert reasoning != payload["messages"][1]["reasoning_content"]


def test_provider_request_proof_compacts_segmented_assistant_text_tail() -> None:
    payload = {
        "messages": [
            {"role": "system", "content": "system prompt\n" + ("s" * 6400)},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "previous result\n" + ("x" * 20_000)}
                ],
            },
            {"role": "user", "content": "每过五分钟提醒我喝水"},
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openrouter",
        proof_budget=12_000,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["retry_count"] == 2
    assert proof["recent_tail_too_large"] is False
    assistant_text = compacted["messages"][1]["content"][0]["text"]
    assert "[provider_request_text_block_compacted:" in assistant_text
    assert assistant_text != payload["messages"][1]["content"][0]["text"]


def test_provider_request_proof_reports_recent_tail_after_tail_compaction_fails() -> None:
    payload = {
        "messages": [
            {"role": "system", "content": "x" * 5000},
            {"role": "user", "content": "hello"},
        ]
    }

    with pytest.raises(ProviderRequestBudgetExceeded) as exc_info:
        prove_or_compact_provider_payload(
            payload,
            projection_adapter="openrouter",
            proof_budget=1000,
            status_projection_mode="content_envelope",
        )

    proof = exc_info.value.proof
    assert proof["fits"] is False
    assert proof["retry_count"] == 2
    assert proof["recent_tail_too_large"] is True


def test_provider_request_proof_emergency_compacts_many_current_turn_tool_results() -> None:
    payload = {
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "research"},
            *[
                {"role": "tool", "tool_call_id": f"call_{index}", "content": "x" * 5000}
                for index in range(80)
            ],
        ]
    }

    compacted, proof = prove_or_compact_provider_payload(
        payload,
        projection_adapter="openrouter",
        proof_budget=96_000,
        status_projection_mode="content_envelope",
    )

    assert proof is not None
    assert proof["fits"] is True
    assert proof["retry_count"] == 3
    assert proof["emergency_current_turn_compacted"] is True
    assert proof["recent_tail_too_large"] is False
    assert compacted["messages"][2]["content"] != payload["messages"][2]["content"]
