"""Codex finding #1 — production stream paths must thread ``chat_app``.

Both ``_stream_response_gateway`` and ``_stream_response_turnrunner`` are the
real REPL stream renderers. Before this fix, they constructed
``StreamingRenderer()`` with no ``chat_app`` kwarg and called the sync
``renderer.append_text(...)`` which writes straight to ``console.file``. The
The output lock + ``_approval_in_flight`` suspend gate therefore never fired
in production — only tests that drove ``ChatApplication.write_through``
directly exercised them.

These tests pin:
  - ``_stream_response_gateway`` passes ``chat_app=`` to the renderer and
    awaits ``aappend_text`` (not ``append_text``) per text-delta event.
  - ``_stream_response_turnrunner`` does the same.
  - When ``_approval_in_flight`` is set on the threaded ``chat_app``, bytes
    do not reach ``console.file`` until the flag clears. This is the
    integration regression that finding #1 enables.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from prompt_toolkit.input.base import DummyInput
from prompt_toolkit.output import DummyOutput

from opensquilla.cli import chat_cmd
from opensquilla.cli.repl.app import ChatApplication
from opensquilla.engine.commands import Surface

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _fresh_chat_app(*, surface: Surface = Surface.CLI_GATEWAY) -> ChatApplication:
    return ChatApplication(
        surface=surface,
        toolbar_context={
            "model": None,
            "session_id": None,
            "suppress": None,
            "status": None,
        },
        bottom_toolbar=lambda: "",
        style=None,
        input=DummyInput(),
        output=DummyOutput(),
    )


class _RecordingRenderer:
    """Stand-in for ``StreamingRenderer`` that records constructor kwargs
    and ``aappend_text`` invocations so the test can assert wiring."""

    last_init_kwargs: dict[str, Any] = {}
    last_instance: _RecordingRenderer | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _RecordingRenderer.last_init_kwargs = dict(kwargs)
        _RecordingRenderer.last_instance = self
        self.appended: list[str] = []
        self.a_appended: list[str] = []
        self.buffer = ""

    def __enter__(self) -> _RecordingRenderer:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def append_text(self, text: str) -> None:
        self.appended.append(text)
        self.buffer += text

    async def aappend_text(self, text: str) -> None:
        self.a_appended.append(text)
        self.buffer += text

    def tool_start(self, *args: Any, **kwargs: Any) -> None:
        return None

    def tool_finished(self, *args: Any, **kwargs: Any) -> None:
        return None

    def pulse(self) -> None:
        return None

    def status(self, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, *args: Any, **kwargs: Any) -> None:
        return None

    def finalize(self, *args: Any, **kwargs: Any) -> None:
        return None

    def stop(self) -> None:
        return None

    def start(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Fix 1 — chat_app wiring through _stream_response_gateway                    #
# --------------------------------------------------------------------------- #


class _FakeGatewayClient:
    """Minimal client surface for ``_stream_response_gateway`` to consume."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    async def send_message(self, *args: Any, **kwargs: Any):
        for event in self._events:
            yield event

    async def resolve_approval(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abort_session(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_stream_response_gateway_threads_chat_app_into_renderer(monkeypatch) -> None:
    """Constructor receives ``chat_app=...``; text deltas go through ``aappend_text``."""

    chat_app = _fresh_chat_app(surface=Surface.CLI_GATEWAY)

    events: list[dict[str, Any]] = [
        {"event": "session.event.text_delta", "text": "hello "},
        {"event": "session.event.text_delta", "text": "world"},
        {"event": "session.event.done", "reason": "stop"},
    ]
    client = _FakeGatewayClient(events)

    monkeypatch.setattr(chat_cmd, "StreamingRenderer", _RecordingRenderer)

    async def _drive() -> None:
        await chat_cmd._stream_response_gateway(
            client,
            "session-key",
            "hello",
            elevated_state=None,
            chat_app=chat_app,
        )

    asyncio.run(_drive())

    assert _RecordingRenderer.last_init_kwargs.get("chat_app") is chat_app, (
        "StreamingRenderer must be constructed with chat_app=... so its "
        "aappend_text path can route writes through the output mutex"
    )
    instance = _RecordingRenderer.last_instance
    assert instance is not None
    assert instance.a_appended == ["hello ", "world"], (
        "production stream gateway must use awaited aappend_text "
        "(not sync append_text) for each text delta"
    )
    assert instance.appended == [], (
        "sync append_text must not be called by the production gateway "
        "stream path — that bypasses the output lock"
    )


def test_stream_response_turnrunner_threads_chat_app_into_renderer(monkeypatch) -> None:
    """``_stream_response_turnrunner`` mirrors the gateway path."""
    from opensquilla.engine.types import DoneEvent, TextDeltaEvent
    from opensquilla.tools.types import ToolContext

    chat_app = _fresh_chat_app(surface=Surface.CLI_STANDALONE)

    # Build a fake TurnRunner that satisfies the isinstance assertion but
    # whose `run` returns a hand-rolled async iterator of engine events.
    events: list[Any] = [
        TextDeltaEvent(text="alpha"),
        TextDeltaEvent(text="beta"),
        DoneEvent(
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cached_tokens=0,
            cost_usd=0.0,
            billed_cost=0.0,
            cost_source="none",
            model="test-model",
        ),
    ]

    async def _stream(*args: Any, **kwargs: Any):
        for event in events:
            yield event

    class _FakeTurnRunner:
        def run(self, *args: Any, **kwargs: Any):
            return _stream()

    fake_runner = _FakeTurnRunner()

    # Make isinstance(..., TurnRunner) pass for our stand-in.
    monkeypatch.setattr(
        chat_cmd, "_wrap_cli_turn_stream", lambda s, _svc: s, raising=False
    )
    monkeypatch.setattr(
        "opensquilla.engine.runtime.TurnRunner", _FakeTurnRunner, raising=True
    )

    # The internal isinstance check on ToolContext still needs to pass.
    fake_ctx = object.__new__(ToolContext)
    monkeypatch.setattr(
        "opensquilla.tools.types.ToolContext", type(fake_ctx)
    )

    monkeypatch.setattr(chat_cmd, "StreamingRenderer", _RecordingRenderer)

    async def _drive() -> None:
        await chat_cmd._stream_response_turnrunner(
            fake_runner,
            "session-key",
            fake_ctx,
            "hello",
            chat_app=chat_app,
        )

    asyncio.run(_drive())

    assert _RecordingRenderer.last_init_kwargs.get("chat_app") is chat_app, (
        "_stream_response_turnrunner must construct StreamingRenderer "
        "with chat_app=... so production tokens route through the "
        "output mutex"
    )
    instance = _RecordingRenderer.last_instance
    assert instance is not None
    assert instance.a_appended == ["alpha", "beta"], (
        "production stream turnrunner must use awaited aappend_text "
        "for each text delta event"
    )
    assert instance.appended == [], (
        "sync append_text must not be called by the production "
        "turnrunner stream path"
    )


def test_production_stream_blocks_during_approval_in_flight(monkeypatch) -> None:
    """Integration regression: bytes do not hit ``console.file`` until the
    inline approval suspend-gate clears.

    Drives the real ``StreamingRenderer`` (not the recorder) through the
    real ``ChatApplication.write_through`` path so the output mutex
    AND the ``_approval_in_flight`` suspend gate are both wired. With
    approval set the awaited write must park; clearing approval unblocks
    it and the bytes land. Without Fix 1 the production paths bypass
    this gate entirely.
    """
    from opensquilla.cli import ui as cli_ui

    chat_app = _fresh_chat_app(surface=Surface.CLI_GATEWAY)
    captured = io.StringIO()
    monkeypatch.setattr(cli_ui.console, "file", captured, raising=True)

    events: list[dict[str, Any]] = [
        {"event": "session.event.text_delta", "text": "CHUNK\n"},
        {"event": "session.event.done", "reason": "stop"},
    ]

    client = _FakeGatewayClient(events)

    async def _drive() -> None:
        # Set approval BEFORE the stream so the write task must park.
        chat_app.set_approval_in_flight(True)
        stream_task = asyncio.create_task(
            chat_cmd._stream_response_gateway(
                client,
                "session-key",
                "hello",
                elevated_state=None,
                chat_app=chat_app,
            )
        )
        # Yield several times so the renderer attempts its first write
        # and parks on `wait_approval_idle`.
        for _ in range(20):
            await asyncio.sleep(0)

        assert "CHUNK" not in captured.getvalue(), (
            "production stream wrote through during the approval window: "
            f"{captured.getvalue()!r}"
        )

        chat_app.set_approval_in_flight(False)
        await asyncio.wait_for(stream_task, timeout=2.0)
        assert "CHUNK" in captured.getvalue()

    asyncio.run(_drive())
