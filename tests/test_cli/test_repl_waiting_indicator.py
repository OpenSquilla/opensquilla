from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.panel import Panel

from opensquilla.cli.repl import stream as stream_module
from opensquilla.cli.repl.prompt import user_input_echo_payload
from opensquilla.cli.repl.stream import StreamingRenderer, UsageSummary, WaitingIndicator


def test_verb_cycles_by_dwell_seconds() -> None:
    ind = WaitingIndicator(started_at=100.0)
    assert ind._verb(0.0) == "Watching"
    assert ind._verb(2.6) == "Tracking"
    assert ind._verb(5.1) == "Sensing"
    n = len(WaitingIndicator._verbs)
    assert ind._verb(n * 2.5 + 0.1) == ind._verb(0.1)


def test_spinner_frame_cycles_by_frame_interval() -> None:
    """The Braille spinner advances one frame per `_spinner_frame_seconds`."""
    ind = WaitingIndicator(started_at=100.0)
    frames = WaitingIndicator._spinner_frames
    interval = WaitingIndicator._spinner_frame_seconds
    assert ind._frame(0.0) == frames[0]
    assert ind._frame(interval + 0.01) == frames[1]
    assert ind._frame(len(frames) * interval + 0.001) == frames[0]


def test_toolbar_text_contains_frame_verb_and_elapsed() -> None:
    started = 100.0
    ind = WaitingIndicator(started_at=started)
    with patch("opensquilla.cli.repl.stream.time.monotonic", return_value=started + 3.0):
        text = ind.toolbar_text()
    # Spinner frame + verb (3.0 / 2.5 = 1 → _verbs[1]) + elapsed.
    assert text.startswith(f"{WaitingIndicator._spinner_frames[0]} ")
    assert "Tracking" in text
    assert "3.0s" in text


def test_waiting_status_renders_as_assistant_header_not_toolbar() -> None:
    """Waiting feedback belongs on the assistant reply row, not the prompt bar."""
    from prompt_toolkit.formatted_text import to_formatted_text

    from opensquilla.cli.repl import prompt as prompt_mod

    previous_status = prompt_mod._toolbar_context.get("status")
    try:
        prompt_mod._toolbar_context["status"] = WaitingIndicator(started_at=100.0)
        with patch(
            "opensquilla.cli.repl.stream.time.monotonic",
            return_value=103.0,
        ):
            toolbar_fragments = to_formatted_text(prompt_mod._bottom_toolbar())
            header_fragments = to_formatted_text(prompt_mod._input_header_fragments())
    finally:
        prompt_mod._toolbar_context["status"] = previous_status

    toolbar_text = "".join(fragment[1] for fragment in toolbar_fragments)
    header_text = "".join(fragment[1] for fragment in header_fragments)
    header_styles = " ".join(fragment[0] for fragment in header_fragments)
    assert "Tracking" not in toolbar_text
    assert header_text.startswith("◢ squilla  ")
    assert "Tracking" in header_text
    assert "3.0s" in header_text
    assert "bg:" not in header_styles


def test_user_input_echo_keeps_marker_and_text_on_one_line() -> None:
    payload = user_input_echo_payload("你好")
    assert "◢" in payload
    assert "you" in payload
    assert "◢ you  \n" not in payload
    assert "你好" in payload


def test_user_input_echo_collapses_large_paste_to_summary() -> None:
    text = "x" * 801
    payload = user_input_echo_payload(text)
    assert "◢" in payload
    assert "you" in payload
    assert "[Pasted Content 801 chars]" in payload
    assert text not in payload


def test_user_input_echo_collapses_many_lines_to_summary() -> None:
    text = "\n".join(f"line {index}" for index in range(11))
    payload = user_input_echo_payload(text)
    assert f"[Pasted Content {len(text)} chars]" in payload
    assert "line 10" not in payload


def test_render_contains_verb_and_elapsed_seconds() -> None:
    started = 100.0
    ind = WaitingIndicator(started_at=started)
    with patch("opensquilla.cli.repl.stream.time.monotonic", return_value=started + 3.0):
        plain = ind.__rich__().plain
    # 3.0 / 2.5 = 1 → _verbs[1] == "Tracking"
    assert "Tracking" in plain
    assert "3.0s" in plain
    assert "Ctrl+C cancels" in plain


def test_pulse_restart_preserves_monotonic_elapsed() -> None:
    started = 100.0
    first = WaitingIndicator(started_at=started)
    second = WaitingIndicator(started_at=started)  # mirrors pulse() re-init
    with patch("opensquilla.cli.repl.stream.time.monotonic", return_value=started + 4.0):
        e1 = first._elapsed()
    with patch("opensquilla.cli.repl.stream.time.monotonic", return_value=started + 5.0):
        e2 = second._elapsed()
    assert e2 >= e1


def test_streaming_renderer_uses_toolbar_status_not_rich_live() -> None:
    """Lock down: pre-token feedback is a live ``WaitingIndicator`` parked
    in the prompt-toolkit assistant header slot, not a Rich ``Live`` region.

    Historical context: a Markdown+Panel Live update loop produced ghost
    panel borders on Windows PowerShell whenever the rendered height grew
    past the visible viewport. Inline approval removed the last remaining
    Live instance and routed waiting feedback through
    ``_toolbar_context['status']``; the header callable pulls the current
    spinner frame on every redraw driven by ``PromptSession.refresh_interval``.
    """
    from opensquilla.cli.repl import prompt as prompt_mod

    # Module no longer carries a Live symbol — that's the canonical
    # regression gate: any future Rich-Live re-introduction would re-bind
    # the attribute, so its absence is load-bearing.
    assert not hasattr(stream_module, "Live"), (
        "stream.py must not import or expose Rich `Live` any more"
    )

    previous_status = prompt_mod._toolbar_context.get("status")
    try:
        prompt_mod._toolbar_context["status"] = None
        with StreamingRenderer() as renderer:
            # Entering the context mounts a live WaitingIndicator.
            mounted = prompt_mod._toolbar_context.get("status")
            assert isinstance(mounted, WaitingIndicator)
            renderer.append_text("foo")
            # First chunk clears the status block before any text writes.
            assert prompt_mod._toolbar_context.get("status") is None
            renderer.append_text("bar")
            renderer.pulse()
        # On stop the status block stays cleared.
        assert prompt_mod._toolbar_context.get("status") is None
    finally:
        prompt_mod._toolbar_context["status"] = previous_status


def test_directive_only_stream_does_not_emit_empty_reply_chrome(monkeypatch) -> None:
    """Control-only chunks should not leave an empty assistant block behind."""
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120, highlight=False)
    monkeypatch.setattr(stream_module, "console", test_console)

    with StreamingRenderer() as renderer:
        renderer.append_text("[[reply_to_current]]")
        renderer.finalize(usage=None)

    output = buf.getvalue()
    assert output == ""
    assert renderer.buffer == ""


def test_visible_stream_opens_single_assistant_marker(monkeypatch) -> None:
    """The assistant marker appears once, only when visible text starts."""
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120, highlight=False)
    monkeypatch.setattr(stream_module, "console", test_console)

    with StreamingRenderer() as renderer:
        renderer.append_text("[[reply_to_current]]")
        renderer.append_text("hello")
        renderer.append_text(" world")
        renderer.finalize(usage=None)

    output = buf.getvalue()
    assert output.count("◢ squilla") == 1
    assert "hello world" in output
    assert renderer.buffer == "hello world"


def test_append_text_writes_plain_to_console_stream(monkeypatch) -> None:
    """Deltas land verbatim on ``console.file`` — no Rich markup processing.

    Model output regularly contains ``[bracket]`` sequences that Rich would
    otherwise parse as markup tags. Routing the stream through
    ``console.file.write`` keeps the bytes untouched and bypasses the Live
    repaint path that previously caused the ghost-panel regression.
    """
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120, highlight=False)
    monkeypatch.setattr(stream_module, "console", test_console)

    with StreamingRenderer() as renderer:
        renderer.append_text("hello ")
        renderer.append_text("[not-markup] ")
        renderer.append_text("world")

    output = buf.getvalue()
    # Bracketed text reaches the terminal verbatim — it was never run
    # through Rich's markup parser.
    assert "[not-markup]" in output
    assert "hello " in output
    assert "world" in output
    assert renderer.buffer == "hello [not-markup] world"


def test_finalize_does_not_re_render_response_as_panel(monkeypatch) -> None:
    """The streamed text is the final view — no post-stream Markdown panel.

    Re-rendering the response after streaming produced a duplicated answer
    in the terminal (plain text once, panel once). Standard agent CLIs
    (Claude Code, codex, aider) leave the streamed output as the final
    view; we match that convention so the user reads the answer exactly
    once.
    """
    captured: list[object] = []

    def fake_print(*args, **kwargs) -> None:
        captured.extend(args)

    monkeypatch.setattr(stream_module.console, "print", fake_print)
    monkeypatch.setattr(stream_module.console, "file", io.StringIO(), raising=False)

    with StreamingRenderer() as renderer:
        renderer.append_text(
            "# heading\n\nbody with **markdown**\n\n| a | b |\n|---|---|\n| 1 | 2 |"
        )
        renderer.finalize(usage=None)

    panels = [obj for obj in captured if isinstance(obj, Panel)]
    assert panels == [], (
        f"finalize must not print a Markdown re-render panel; got {len(panels)}"
    )
    # The dim footer (usage/elapsed) is still emitted as a plain string.
    assert any(isinstance(obj, str) and "0.0" in obj for obj in captured)


@pytest.mark.parametrize(
    ("hostile", "label"),
    [
        ("\x1b[2J\x1b[H", "CSI clear-screen + cursor-home"),
        ("\x1b]0;pwned\x07", "OSC 0 set-title (BEL terminator)"),
        ("\x1b]52;c;cGF5bG9hZA==\x1b\\", "OSC 52 clipboard write (ST terminator)"),
        ("\x1bPtmux;esc\x1b\\", "DCS programmable string"),
        ("\x1bc", "ESC c full terminal reset"),
        ("hello\rOVERWRITE", "CR line-overwrite"),
        ("ding\x07ding", "BEL"),
        ("back\x08space", "backspace"),
    ],
)
def test_append_text_strips_terminal_control_sequences(
    monkeypatch, hostile: str, label: str
) -> None:
    """Untrusted model deltas must not drive the terminal emulator."""
    buf = io.StringIO()
    test_console = Console(
        file=buf, force_terminal=False, width=120, highlight=False
    )
    monkeypatch.setattr(stream_module, "console", test_console)

    with StreamingRenderer() as renderer:
        renderer.append_text(hostile)

    output = buf.getvalue()
    # No ESC byte and no surviving C0 control besides newline/tab can reach
    # the terminal — those are the bytes that would drive cursor/colour/
    # clipboard/title behaviour.
    assert "\x1b" not in output, f"ESC leaked for {label}: {output!r}"
    assert "\r" not in output
    assert "\x07" not in output
    assert "\x08" not in output
    # The renderer's in-memory buffer (used as TurnResult.text and the
    # source of the final Markdown panel) must mirror the same scrubbing
    # so /save and the post-stream panel re-render are equally safe.
    assert "\x1b" not in renderer.buffer
    assert "\r" not in renderer.buffer


def test_append_text_keeps_newlines_and_tabs(monkeypatch) -> None:
    """Sanitization must not destroy Markdown's structural whitespace."""
    buf = io.StringIO()
    test_console = Console(
        file=buf, force_terminal=False, width=120, highlight=False
    )
    monkeypatch.setattr(stream_module, "console", test_console)

    payload = "# heading\n\n- item one\n- item two\n\tindented"
    with StreamingRenderer() as renderer:
        renderer.append_text(payload)

    assert renderer.buffer == payload
    assert "# heading" in buf.getvalue()
    assert "\tindented" in buf.getvalue()


def _usage(turn_cost: float = 0.5) -> UsageSummary:
    return UsageSummary(
        input_tokens=10,
        output_tokens=20,
        cost_usd=turn_cost,
        model="deepseek/v4-flash",
    )


def test_footer_renders_per_turn_cost() -> None:
    """Footer shows per-turn cost; no cumulative segment."""
    renderer = StreamingRenderer()
    line = renderer.footer(_usage(turn_cost=0.123456), elapsed=1.0)
    assert "$0.123456" in line
    assert "∑" not in line


def test_footer_skips_cost_when_turn_cost_zero() -> None:
    """Free-tier turns with zero cost don't render a cost segment."""
    renderer = StreamingRenderer()
    line = renderer.footer(_usage(turn_cost=0.0), elapsed=1.0)
    assert "$" not in line, line
