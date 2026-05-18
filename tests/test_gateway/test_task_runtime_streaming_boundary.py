from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from opensquilla.engine.types import DoneEvent, ErrorEvent, TextDeltaEvent


def _streaming_module() -> Any:
    return import_module("opensquilla.gateway.task_runtime_streaming")


async def _collecting_emitter(
    emitted: list[tuple[str, str, dict[str, Any]]],
    session_key: str,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    emitted.append((session_key, event_name, payload))


def _emitter_for(
    emitted: list[tuple[str, str, dict[str, Any]]],
) -> Callable[[str, str, dict[str, Any]], Awaitable[None]]:
    async def _emitter(
        session_key: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        await _collecting_emitter(emitted, session_key, event_name, payload)

    return _emitter


def test_task_runtime_streaming_module_exports_emitter() -> None:
    streaming = _streaming_module()

    assert callable(streaming.emit_task_runtime_stream_events)


def test_boot_preserves_compatibility_alias_or_short_delegator() -> None:
    from opensquilla.gateway import boot

    streaming = _streaming_module()

    assert callable(boot._emit_task_runtime_stream_events)
    if boot._emit_task_runtime_stream_events is streaming.emit_task_runtime_stream_events:
        return

    source = Path("src/opensquilla/gateway/boot.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="src/opensquilla/gateway/boot.py")
    definitions = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_emit_task_runtime_stream_events"
    ]
    assert len(definitions) == 1
    body = [
        node
        for node in definitions[0].body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    assert len(body) == 1
    assert isinstance(body[0], ast.Return)
    assert "emit_task_runtime_stream_events" in ast.unparse(body[0])


@pytest.mark.asyncio
async def test_error_event_iteration_timeout_emits_terminal_payload_and_raises_raw_error() -> None:
    streaming = _streaming_module()
    emitted: list[tuple[str, str, dict[str, Any]]] = []

    async def _stream():
        yield ErrorEvent(
            message="Iteration 1 exceeded iteration_timeout",
            code="iteration_timeout",
        )

    with pytest.raises(RuntimeError, match="Iteration 1 exceeded iteration_timeout"):
        await streaming.emit_task_runtime_stream_events(
            _stream(),
            "agent:main:test",
            _emitter_for(emitted),
            stream_event_sink=None,
            idle_timeout=1.0,
            heartbeat_interval=0.0,
        )

    assert emitted == [
        (
            "agent:main:test",
            "session.event.error",
            {
                "message": "The task timed out before it could finish.",
                "code": "iteration_timeout",
                "terminal_message": "The task timed out before it could finish.",
                "terminal_reason": "timeout",
                "error_message": "Iteration 1 exceeded iteration_timeout",
            },
        )
    ]


@pytest.mark.asyncio
async def test_stream_event_sink_failures_are_logged_and_do_not_block_emission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streaming = _streaming_module()
    emitted: list[tuple[str, str, dict[str, Any]]] = []
    sink_events: list[Any] = []
    log_calls: list[tuple[str, dict[str, Any]]] = []

    def _debug(event_name: str, **kwargs: Any) -> None:
        log_calls.append((event_name, kwargs))

    def _sink(event: Any) -> None:
        sink_events.append(event)
        raise RuntimeError("sink failed")

    async def _stream():
        yield TextDeltaEvent(text="hello")
        yield DoneEvent(text="done")

    monkeypatch.setattr(streaming.log, "debug", _debug)

    await streaming.emit_task_runtime_stream_events(
        _stream(),
        "agent:main:test",
        _emitter_for(emitted),
        stream_event_sink=_sink,
        idle_timeout=1.0,
        heartbeat_interval=0.0,
    )

    assert [event.text for event in sink_events] == ["hello", "done"]
    assert emitted == [
        ("agent:main:test", "session.event.text_delta", {"text": "hello"}),
        (
            "agent:main:test",
            "session.event.done",
            {
                "text": "done",
                "input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "cached_tokens": 0,
                "iterations": 0,
                "cost_usd": 0.0,
                "billed_cost": 0.0,
                "cost_source": "none",
                "model": "",
                "runtime_context_hash": None,
                "runtime_context_chars": 0,
                "routed_tier": None,
                "routing_source": "none",
                "routing_confidence": 0.0,
                "baseline_model": "",
                "routed_model": "",
                "savings_pct": 0.0,
                "savings_usd": 0.0,
                "cache_hit_active": False,
                "total_savings_pct": 0.0,
                "total_savings_usd": 0.0,
                "cache_write_tokens": 0,
                "reasoning_content": None,
            },
        ),
    ]
    assert [call[0] for call in log_calls] == [
        "task_runtime.stream_event_sink_failed",
        "task_runtime.stream_event_sink_failed",
    ]
    assert [call[1]["event_kind"] for call in log_calls] == ["text_delta", "done"]
